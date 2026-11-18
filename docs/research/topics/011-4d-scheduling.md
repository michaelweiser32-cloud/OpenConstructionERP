# 011. 4D Scheduling: Linking BIM Elements to Schedule Activities and Timeline Simulation

## What it does
4D scheduling connects model elements (walls, slabs, columns) to schedule activities, so a planner can play the construction sequence on a timeline: elements show up as "not started", "in progress" or "complete" on any date. Typical uses are checking the sequence before a bid, explaining phasing to a client or site team, spotting logic errors (a roof before its columns), and comparing planned and actual progress. Commercial tools such as Bentley SYNCHRO 4D, Navisworks TimeLiner and Fuzor charge for each seat and run on the desktop.

## Already in the codebase (with file paths)
Much of the basic plumbing already exists. The gap is mainly in workflow and automation.
- `backend/app/modules/schedule/models.py`: the `Activity.bim_element_ids` JSON column, commented as being "for 4D linking".
- `backend/app/modules/schedule/router.py`: `PUT /activities/{id}/bim-links/`, `GET /activities/by-bim-element/`, Gantt data, CPM calculation, baselines, progress updates, risk analysis, `generate-from-boq`, and import from Primavera XER and MS Project XML.
- `frontend/src/shared/ui/BIMViewer/use4dTimeline.ts`, `4dStatus.ts`, `TimelineScrubber.tsx`: a timeline with play, pause and speed controls, plus an element-to-activity map used to colour elements by status. `BIMViewer.tsx` shows it in the `4d_schedule` colour mode.
- `frontend/src/features/bim/LinkActivityToBIMModal.tsx`: manual linking.
- `frontend/src/features/bim/BIMPage.tsx` (around line 2434): the "4D Schedule" toolbar button is disabled and marked "coming soon".

**Gaps:**
1. No rule-based auto-linking. Elements can't be linked to activities by storey/level, category, classification code or BOQ position, so linking is entirely manual, which is the biggest time cost.
2. No dedicated 4D panel. The toolbar button is still disabled.
3. The timeline shows planned dates only. It doesn't compare actual progress (from progress updates) or a baseline.
4. No validation rules for 4D: elements with no activity, activities with no elements, or a sequence that contradicts element dependencies such as level order.
5. No way to export the simulation for clients, as a video, GIF or shareable link.
6. No combined 4D and 5D cash-flow view, even though a `5d_cost` mode already exists.

## Who it helps and how much
- **Small general contractors and estimators bidding with a model:** Medium-High. A 4D animation helps win bids and shows the logistics plan without a SYNCHRO seat, which Bentley lists from about $4,980 a year.
- **Site managers:** Medium. Seeing planned and actual status by storey makes weekly look-ahead planning easier.
- **Very small firms working only from 2D PDFs:** Low. They have no model to link.

Most of the value depends on auto-linking. Linking elements by hand rarely pays off for small teams.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Mostly extensions to the `schedule` and `bim_hub` modules and the BIM frontend. No new heavy dependencies.
- Backend: add `POST /schedules/{id}/auto-link-bim/`. It would take rule definitions (match on level, category, classification `din276`/`masterformat`, or the activity's linked BOQ position, then follow that position's `cad_element_ids`) and return proposed links with confidence scores. The user confirms them before anything is saved, in line with the "AI-augmented, human-confirmed" principle. Publish a `schedule.bim_links.updated` event on the event bus.
- Validation: add 4D rules (`schedule_4d.unlinked_elements`, `schedule_4d.empty_activity`, `schedule_4d.level_sequence`) to the validation engine.
- Frontend: turn on the 4D panel in `BIMPage.tsx` (a Gantt next to the viewer, with selection synced both ways), add a toggle between planned, actual and baseline status, and record the canvas to WebM with the browser `MediaRecorder` API (no dependency).

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **MPXJ** (https://github.com/joniles/mpxj): reads and writes XER, MPP, MSPDI, Asta, Synchro and more. LGPL-2.1, and it has a Python wrapper. It needs a JVM, so it should be an optional module rather than part of core.
- **xeokit-bim-viewer** (https://github.com/xeokit/xeokit-bim-viewer): a web BIM viewer. AGPL-3.0; a reference only, since it duplicates the existing Three.js viewer.
- **Bonsai 4D work in progress** (https://github.com/Svisuals/4D_Bonsai): a useful design reference for the user experience. It's based on IfcOpenShell, which project policy rules out, so its code can't be reused.
- **Schedule MCP servers:** p6xer-mcp-server (https://pypi.org/project/p6xer-mcp-server, MIT according to its listing) and project-mcp (https://github.com/jeffmodeler/project-mcp). Both are community projects I haven't vetted. Neither offers BIM-to-schedule linking; they only analyse schedule files.
- **Browser MediaRecorder API** (https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder): built into the browser and free, for exporting the timeline as video.
- I found no open-source MCP server or connector that links BIM elements to schedule activities.

## Priority: 3/5 — most of the core already exists; auto-linking plus a dedicated 4D panel would turn it into a strong low-cost alternative to SYNCHRO, but the market of small firms that work with a model is limited.

## Sources
- https://www.bentley.com/products/synchro-4d
- https://www.capterra.com/p/35289/Synchro/
- https://softwarefinder.com/construction/fuzor
- https://github.com/joniles/mpxj
- https://github.com/xeokit/xeokit-bim-viewer
- https://community.osarch.org/discussion/comment/27307
- https://osarch.org/2026/05/29/bonsai-viewer-is-coming/
- https://pypi.org/project/p6xer-mcp-server
- https://github.com/jeffmodeler/project-mcp
- https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder
