# 099. Bluebeam integration (Studio API, markups exchange, Revu)

## What it does
Bluebeam Revu is the de-facto PDF markup and takeoff tool in many North American and UK/AU estimating shops. An integration would let an estimator (a) import Revu markups/measurements (Markups List exported as CSV/XML, or `.bax` markup files) into the ERP as markups and takeoff quantities linked to BOQ positions, (b) export ERP markups back as a Revu-readable file, and (c) optionally sync with Bluebeam Studio Sessions/Projects in the cloud (create session, upload PDF, invite reviewers, pull markups) via the Studio REST API.

## Already in the codebase (with file paths)
- `backend/app/modules/markups/` (models, router, service): markups table with type/geometry/text/color/status/label, scale calibration, stamp templates, bulk create (`POST /bulk/`), link-to-BOQ (`POST /{id}/link-to-boq/`), and CSV export only (`GET /export/`, format pattern `^csv$`).
- `frontend/src/features/markups/` (`InlinePdfAnnotator.tsx`, `UnifiedMarkupsList.tsx`, `aggregator.ts`): in-app PDF annotation and unified list.
- `backend/app/modules/takeoff/`, `dwg_takeoff/`: native takeoff.
- No Bluebeam-specific code found (grep for bluebeam/revu/bax returned nothing relevant). Gap: no importer for Revu CSV/XML/BAX, no Studio API client, no OAuth connector.

## Who it helps and how much
- Small estimators/subs who already measure in Revu: high value. A Markups List CSV/XML import turns existing Revu takeoffs (Subject, Label, Measurement, Unit, Page, Layer) into BOQ quantities without re-measuring; this is the cheapest big win.
- Teams reviewing drawings with GCs who run Studio Sessions: medium value; requires paid Bluebeam tiers (Basics cannot create Sessions/Projects or use the Developer Portal; US list prices roughly 260/330/440 USD per user/year for Basics/Core/Complete, Max at an introductory 590 USD) and production app approval from Bluebeam.
- Shops without Bluebeam: none; the native markups module already covers them.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
- Phase A, Small: file-based exchange inside `markups` (or new `oe_bluebeam` module depending on `oe_markups`, `oe_boq`). Parser for Revu Markups List CSV/XML summary (column mapping configurable, since Revu columns are user-customisable) and `.bax` (Bluebeam XML) -> `MarkupCreate` list -> existing bulk endpoint. Add validation rules (unit recognised, scale/measurement present, duplicate subjects) per the validation-first rule; then a "map to BOQ position" review screen (human-confirmed). Export: extend `/export/` with an XML option.
- Phase B, Medium: `oe_bluebeam` connector under `integrations`: OAuth 2.0 authorization-code flow (`api.bluebeam.com/oauth2/authorize` and `/oauth2/token`, region-specific hosts e.g. AU), Studio Sessions client (create session, add file with upload + confirm-upload, invite users, snapshot download, list markups via v2 endpoint). Background job via event bus; tokens stored encrypted per tenant.
- Phase C (optional): document Bluebeam Max local MCP alongside the ERP MCP tools; no server work needed.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- Bluebeam Studio API (REST, OAuth 2.0): https://support.bluebeam.com/developer/authentication-guide.html, session guide https://support.bluebeam.com/developer/studio-session-guide.html. Free API, but needs Core/Complete/Max subscription and Bluebeam production approval.
- Revu Markups List export (CSV/XML/PDF summary) and BAX import/export: https://support.bluebeam.com/user-manual/menus/window/markups-list.html. No licence cost beyond Revu; Basics is limited to PDF summary output in Revu 21.
- `@lineai/bluebeam-api` (unofficial TypeScript client, reference only): https://app.unpkg.com/@lineai/bluebeam-api@0.0.6/files/README.md. Licence not verified.
- Python stdlib `csv` / `xml.etree` (or `defusedxml`, PSF licence) for parsing; `httpx` (BSD) for the API client, both lightweight.
- Bluebeam MCP: Bluebeam ships a local MCP server with Revu (Max tier; AnythingLLM setup documented): https://support.bluebeam.com/revu/how-to/mcp-anything.html. It is a desktop-local server, not a cloud API; no official public cloud MCP server for Studio was found.

## Priority: 3/5 — file-based CSV/XML/BAX import is cheap and valuable for Revu-using estimators; the Studio API sync is gated by paid tiers and vendor approval, so defer it.

## Sources
- https://support.bluebeam.com/developer/getting-started-dev-portal.html
- https://support.bluebeam.com/developer/authentication-guide.html
- https://support.bluebeam.com/developer/studio-session-guide.html
- https://support.bluebeam.com/user-manual/menus/window/markups-list.html
- https://support.bluebeam.com/online-help/revu20/Content/RevuHelp/Menus/Window/Panels/Markups/Markups-List--MTV.htm
- https://support.bluebeam.com/revu/how-to/mcp-anything.html
- https://community.bluebeam.com/discussion/7846/file-downloads-with-markups-for-studio-sessions-via-api
- https://www.bluebeam.com/solutions/compare
- https://app.unpkg.com/@lineai/bluebeam-api@0.0.6/files/README.md
