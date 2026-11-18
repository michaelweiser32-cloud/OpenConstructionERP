# 081. Mobile PWA and offline mode (service workers, IndexedDB sync, conflict resolution)

## What it does
Lets the web app be installed on phones and tablets as a Progressive Web App and keep working without a connection, for example in a basement, on a remote site or at a client meeting with bad signal. It has three parts:
1. **App shell offline.** A service worker precaches the built JS, CSS, fonts and i18n bundles, so the app still opens with no network.
2. **Data offline.** Recently viewed projects, BOQs, punch lists and field reports are read from IndexedDB, and edits are queued locally.
3. **Sync and conflict resolution.** When the device reconnects, queued edits are replayed safely. Retries never create duplicates, and if someone else changed the same record, the user is shown the difference instead of losing data without notice.

## Already in the codebase (with file paths)
- `frontend/src/shared/lib/offlineStore.ts` is a raw IndexedDB layer with no dependencies (`oe_offline` DB). It has an `apiCache` store with a 1-hour TTL and an auto-increment `mutationQueue`.
- `frontend/src/shared/lib/api.ts`: when a request hits a network error and the device is offline, GETs are served from the cache and POST/PUT/PATCH/DELETE are queued, with a "Saved offline" toast. Successful GET responses are cached.
- `frontend/src/shared/hooks/useOnlineStatus.ts` replays the queue in order when the device comes back online.
- `frontend/src/main.tsx` sets React Query `networkMode: 'offlineFirst'`.
- `frontend/index.html` has a `theme-color` meta tag only.
- `yjs` and `y-websocket` are already dependencies (`frontend/package.json`, `frontend/src/modules/collaboration/`).

**Gaps:**
- There is no service worker or web app manifest, so a cold start offline fails and the app cannot be installed.
- During replay, a **409 is treated as success and the mutation is deleted**. A real edit conflict is therefore dropped without notice.
- Queued mutations carry no base version and no idempotency key, so a retried POST can create duplicates.
- Expired cache entries are discarded even while the device is offline. There is no "make this project available offline" pinning.
- Yjs documents have no local persistence (`y-indexeddb` is missing).
- Nothing calls `navigator.storage.persist()`. Safari can evict script-writable storage after 7 days without user interaction, unless the app is installed to the home screen.

## Who it helps and how much
- **Site managers and foremen** doing punch lists, field reports, inspections, safety checks and photos: high value. This is the main mobile use case, and connectivity on site is often poor.
- **Estimators** reviewing a BOQ at a client meeting or while travelling: medium value. They mostly read, and occasionally edit.

For a small firm, "it works on my phone in the basement" is a deciding factor when choosing a tool. The silent data loss on a 409 is a trust problem as well as a missing feature.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium overall.** It splits into three steps:
- **S: shell and installability.** Add `vite-plugin-pwa` (dev dependency, `generateSW`): precache the build, serve a `NetworkFirst` fallback for `/api` GETs, and generate a manifest with icons.
- **M: safe sync.**
  - Add a `version` column (or use `updated_at`) on mutable entities: BOQ positions, punch items, field reports.
  - The backend accepts `If-Match` / `base_version` and returns 409 with the current server row.
  - Add an `Idempotency-Key` header, stored in a small core table with a TTL, so replays never duplicate records.
  - The queue stores `base_version`, the key and the entity ref. On 409 the item goes to a "conflicts" store and the UI offers keep mine / keep theirs / merge per field.
  - Never auto-discard queued edits.
- **M: per-project offline pinning.** Pinned projects get no TTL. Photo blobs are stored in IndexedDB and uploaded later. Call `navigator.storage.persist()`.
- **Optional:** use `y-indexeddb` for collaborative BOQ editing, so CRDT merges handle conflicts natively.

**Plugging into the module system:**
- A core `offline` capability in `backend/app/core`: an idempotency middleware plus a versioning mixin.
- Modules opt in with an `offline: {entities: [...]}` declaration in `manifest.py`, and the frontend `manifest.ts` declares which routes and queries to prefetch for pinned projects.
- Validation still runs on the server when queued items are replayed. Validation errors join the conflict queue so a person reviews them.

**Platform limit:** iOS Safari does not support the Background Sync API, so replay has to stay in the foreground (on app open or the `online` event) as the primary path. Workbox background sync is only an extra on Chromium.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **vite-plugin-pwa**: https://vite-pwa-org.netlify.app/ (MIT). Wraps Workbox.
- **Workbox**: https://github.com/GoogleChrome/workbox (MIT). Precaching, runtime caching, background sync.
- **y-indexeddb**: https://github.com/yjs/y-indexeddb (MIT, from the Yjs org). Offline persistence for the Yjs docs already in use.
- **Dexie.js**: https://github.com/dexie/Dexie.js (Apache-2.0). Optional, if the raw IndexedDB code becomes hard to maintain. Dexie Cloud is a separate paid product.
- **MCP servers:** none relevant. Offline sync is a client and protocol concern. I found no credible MCP server for it.

## Priority: 4/5 — the plumbing is mostly there, but the 409 data-loss bug and the missing service worker block real use on site
The IndexedDB cache and mutation queue already exist. A service worker, manifest, versioning with idempotency keys and a conflict UI would turn a fragile feature into a reliable mobile field tool for small contractors.

## Sources
- https://vite-pwa-org.netlify.app/guide/service-worker-strategies-and-behaviors
- https://github.com/GoogleChrome/workbox
- https://caniuse.com/background-sync
- https://developer.chrome.com/blog/background-sync
- https://web.dev/articles/storage-for-the-web
- https://docs.yjs.dev/getting-started/allowing-offline-editing
- https://github.com/yjs/y-indexeddb
- https://github.com/dexie/Dexie.js
