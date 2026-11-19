import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { AuthedImg } from './AuthedImg';
import { useAuthStore } from '@/stores/useAuthStore';

describe('AuthedImg', () => {
  const createObjectURL = vi.fn(() => 'blob:synthetic-photo');
  const revokeObjectURL = vi.fn();

  beforeEach(() => {
    useAuthStore.setState({ accessToken: 'synthetic-access-token' });
    Object.assign(URL, { createObjectURL, revokeObjectURL });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
  });

  it('fetches with the bearer token and renders the blob URL', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, blob: async () => new Blob(['png-bytes']) }));
    vi.stubGlobal('fetch', fetchMock);

    const { unmount } = render(<AuthedImg src="/api/v1/documents/photos/p1/thumb/" alt="site" />);

    await waitFor(() => expect(screen.getByAltText('site')).toHaveAttribute('src', 'blob:synthetic-photo'));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/v1/documents/photos/p1/thumb/');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer synthetic-access-token');
    // The token never ends up in the rendered markup.
    expect(document.body.innerHTML).not.toContain('synthetic-access-token');

    unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:synthetic-photo');
  });

  it('renders a broken image (so onError fallbacks fire) when the request is refused', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, blob: async () => new Blob([]) })));

    render(<AuthedImg src="/api/v1/documents/photos/p2/file" alt="refused" />);

    await waitFor(() => expect(screen.getByAltText('refused')).toHaveAttribute('src', 'data:,'));
    expect(createObjectURL).not.toHaveBeenCalled();
  });
});
