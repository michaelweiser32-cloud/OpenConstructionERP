import type { ImgHTMLAttributes } from 'react';
import { useAuthedObjectUrl } from '../hooks/useAuthedObjectUrl';

// An empty data URI never decodes, so the browser fires the normal `error`
// event and callers' existing `onError` fallbacks keep working.
const BROKEN_IMAGE_SRC = 'data:,';

/**
 * `<img>` for images behind authenticated API routes (e.g. project photos).
 *
 * Loads `src` with the user's bearer token via {@link useAuthedObjectUrl}
 * and renders the resulting object URL. While loading nothing is fetched by
 * the `<img>` itself; on failure the image errors like a normal broken image.
 */
export function AuthedImg({ src, ...rest }: ImgHTMLAttributes<HTMLImageElement> & { src: string }) {
  const state = useAuthedObjectUrl(src);
  if (state.status === 'ready') return <img src={state.url} {...rest} />;
  if (state.status === 'error') return <img src={BROKEN_IMAGE_SRC} {...rest} />;
  return <img {...rest} aria-busy="true" />;
}
