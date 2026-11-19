import { useEffect, useState } from 'react';
import { useAuthStore } from '../../stores/useAuthStore';

export type AuthedObjectUrlState =
  | { status: 'idle' | 'loading'; url: undefined }
  | { status: 'ready'; url: string }
  | { status: 'error'; url: undefined };

/**
 * Fetch a protected binary (e.g. a photo) with the user's bearer token and
 * expose it as a short-lived `blob:` object URL.
 *
 * Plain `<img src="/api/...">` cannot send an `Authorization` header, so
 * protected image routes would always answer 401. Fetching with the header
 * keeps the token out of URLs (no `?token=` in logs, history or Referer).
 * The object URL is revoked when the component unmounts or `src` changes.
 */
export function useAuthedObjectUrl(src: string | null | undefined): AuthedObjectUrlState {
  const [state, setState] = useState<AuthedObjectUrlState>({ status: 'idle', url: undefined });

  useEffect(() => {
    if (!src) {
      setState({ status: 'idle', url: undefined });
      return undefined;
    }
    const controller = new AbortController();
    let objectUrl: string | undefined;
    let cancelled = false;
    setState({ status: 'loading', url: undefined });

    const token = useAuthStore.getState().accessToken;
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;

    fetch(src, { headers, signal: controller.signal, credentials: 'same-origin' })
      .then((resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setState({ status: 'ready', url: objectUrl });
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'error', url: undefined });
      });

    return () => {
      cancelled = true;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);

  return state;
}
