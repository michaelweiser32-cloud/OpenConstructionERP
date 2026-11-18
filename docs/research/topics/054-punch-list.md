# 054. Punch list workflow (pins on drawings, photos, assignees, sign-off)

## What it does
A punch list (snag list) records defects and incomplete work near handover. A typical field workflow: walk the site with a tablet, drop a pin on the drawing sheet, take one or more photos, assign a trade or subcontractor with a due date, let the assignee mark it fixed, then have a different person verify it and sign it off before it is closed. Commercial tools (Procore, Fieldwire) add an automatic "ball in court" field (who has to act next), separate manager and final-approver roles, distribution emails, and PDF reports with pins and photos.

## Already in the codebase (with file paths)
The backend is fairly complete. The frontend is the main gap.
- `backend/app/modules/punchlist/models.py`: `PunchItem` with `document_id`, `page`, `location_x/y` (pin), `photos` (JSON list), `assigned_to`, `due_date`, `trade`, `priority`, `resolved_at`, `verified_at/verified_by`, `metadata_`.
- `backend/app/modules/punchlist/service.py`: a status state machine (`open -> in_progress -> resolved -> verified -> closed`, plus reopen). It requires the verifier to be a different user from the resolver, blocks closing critical items in some cases, and computes summary statistics (average days to close).
- `backend/app/modules/punchlist/router.py`: CRUD, `/transition/`, `/pin-to-sheet/`, photo upload and delete, `/summary/`, `/export/pdf/` and `/export/excel/`.
- `frontend/src/features/punchlist/PunchListPage.tsx` and `api.ts`: a list or board view with filters and a photo counter. I found no UI that places or shows pins on a sheet, even though the backend endpoint exists. I also found no camera capture.
- A reusable PDF viewer and annotator already exists: `frontend/src/features/markups/InlinePdfAnnotator.tsx` and `frontend/src/modules/pdf-takeoff/`, using `pdfjs-dist`.
- The AI chat already understands punch items: `backend/app/modules/erp_chat/tools.py` (for example "open punch list items about doors").
- Missing:
  - no event-bus publish on status changes, so assignees get no notifications;
  - no ball-in-court field;
  - no captured signature or sign-off certificate;
  - no offline mode.

## Who it helps and how much
- **Small general contractors and fit-out firms:** high value. Handover snagging is a recurring pain, and per-seat SaaS is expensive. Fieldwire's help center lists $54 to $104 per user per month, with a free Basic tier for up to five users.
- **Subcontractors:** they get a clear list of their own items and due dates.
- **Estimators:** moderate value. Closed-out defects can feed back costs through change orders and lessons learned.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Modules touched: `punchlist`, `notifications`, `documents`/`markups` (viewer reuse), and optionally `integrations`.
1. **Pin-on-sheet UI.** Reuse the markups PDF viewer. Clicking on a sheet calls `pin-to-sheet` with normalized coordinates. Draw coloured pins by status (open, resolved, closed) on that sheet.
2. **Mobile photo capture.** Use `<input type="file" accept="image/*" capture="environment">`. Compress on the client, make thumbnails on the server, and strip EXIF GPS data unless the user opts in.
3. **Events.** Publish `punchlist.item.assigned`, `.resolved` and `.verified` on the core event bus. The `notifications` module and the email, Slack or Teams integrations subscribe to them.
4. **Ball in court.** Derive it from status (open or in_progress means the assignee, resolved means the verifier, verified means the approver). Add a "My items" filter.
5. **Sign-off.** Capture a signature with signature_pad, store it as an image next to `verified_by` and a timestamp, and include it in the PDF export as a close-out certificate.
6. **Validation.** Add rules to a `project_completeness` rule set, for example "no open critical punch items before handover" and "overdue items".
7. **Later: offline PWA** using Workbox with a background-sync queue.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **pdf.js** (`pdfjs-dist`, already a dependency): https://github.com/mozilla/pdf.js. Apache-2.0.
- **signature_pad**: https://github.com/szimek/signature_pad. MIT, no dependencies, works in desktop and mobile browsers.
- **Workbox** (offline caching and background sync): https://developer.chrome.com/docs/workbox. MIT.
- **Pillow** (server-side thumbnails and EXIF stripping): https://github.com/python-pillow/Pillow. MIT-CMU (HPND).
- **Procore Punch API**, for import or export by teams that also use Procore: punch items are exposed under `/rest/v1.x/punch_items`. Procore's docs describe Ball in Court as read-only and driven by status. Requires a Procore account and app registration.
- **Community Procore MCP server** (TylerIlunga/procore-mcp-server): its directory listing shows create, list and update punch-item tools. It is unofficial; I could not check its maintenance or license from the repo itself.
- I found no official, vendor-neutral punch-list MCP server. Exposing this module's own endpoints through `erp_chat` tools is the realistic route.

## Priority: 4/5 — the backend already covers most of this, so a pin-on-drawing UI, photo capture, notifications and signature sign-off would turn it into a feature small contractors use every day, and it competes with $50+ per-seat tools.

## Sources
- https://support.procore.com/procore-mobile-android/user-guide/drawings-android/tutorials/add-punch-list-items-to-a-drawing-android
- https://v2.support.procore.com/process-guides/assets-user-guide/create-punch-list-item/
- https://hexdocs.pm/procore_sdk/Procore.Model.PunchItem.html
- https://glama.ai/mcp/servers/TylerIlunga/procore-mcp-server/tools/create_punch_item
- https://help.fieldwire.com/hc/en-us/articles/202634054
- https://github.com/szimek/signature_pad
- https://github.com/mozilla/pdf.js
- https://developer.chrome.com/docs/workbox
