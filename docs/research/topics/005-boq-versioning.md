# 005. BOQ versioning, revisions, snapshots and side-by-side compare

## What it does
Lets an estimator freeze the state of a Bill of Quantities at key moments (first draft, sent to client, after value engineering, awarded), branch a revision, and later answer the question "what changed between Rev A and Rev C, and why did the total go up by 4 %?". A useful compare is **position-level**: which items were added or removed, and which changed quantity, unit rate, description or markup. It also shows the cost impact of each change and can be exported (PDF/Excel) for the client or for a change-order discussion.

## Already in the codebase (with file paths)
Most of the foundation is already there:
- `backend/app/modules/boq/models.py`: `BOQ` has lock and revision fields (`is_locked`, `parent_estimate_id`, `estimate_type`, `approved_by/at`, `base_date`). `BOQSnapshot` (`oe_boq_snapshot`) stores a full JSON `snapshot_data`.
- `backend/app/modules/boq/service.py` (`create_snapshot`, ~L2909) serialises positions and markups. Restore exists.
- `backend/app/modules/boq/router.py` has these endpoints: `GET/POST /boqs/{id}/snapshots/`, `POST /boqs/{id}/restore/{snapshot_id}`, `POST /boqs/{id}/lock/`, `/unlock/`, `POST /boqs/{id}/create-revision/` (duplicates the BOQ and links it via `parent_estimate_id`), and `GET /boqs/{id}/activity/`.
- `frontend/src/features/boq/VersionHistoryDrawer.tsx`: timeline with restore. It shows only an *aggregate* delta (position count and total) between consecutive snapshots.
- `frontend/src/features/boq/BOQListPage.tsx` (`CompareModal`): compares two BOQs on the client, **section-level only**, matched by ordinal or description.

**Gaps:**
1. There is no backend diff endpoint or service, and no diff at position level.
2. Snapshots don't store position IDs, so matching has to fall back on ordinals, which breaks when items are renumbered.
3. No automatic snapshot on lock, export, tender submission or revision creation, e.g. via the event bus.
4. No diff export (Excel/PDF) and no "compare snapshot vs live" or "Rev A vs Rev C" UI.
5. No validation rule that flags large unexplained deltas between revisions.

## Who it helps and how much
Small estimating firms re-price the same job 3–6 times: client scope changes, supplier price updates, VE rounds. Today they keep "Estimate_v3_FINAL2.xlsx" copies and compare them by eye. A clear position-level diff saves roughly 30–90 minutes per revision cycle. It also cuts disputes ("you never told us the slab went up"), and it feeds change orders directly. The value is high and broad, because every user of the BOQ module benefits.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch)
**Small to Medium**, done entirely inside `boq`, with an optional hook into `changeorders` and `validation`.
- Add `position_id` (and section id) to the snapshot payload, keeping it backward compatible: match old snapshots by ordinal and then by fuzzy description.
- `service.diff(a, b)`, where a and b can each be a snapshot, a live BOQ or a revision. It returns `{added, removed, changed[{field, old, new, delta_total}], markup_changes, totals}`. A plain-Python dict comparison is enough, so no new dependency is needed. DeepDiff is optional.
- Endpoint `GET /boqs/{id}/compare?left=snap:<id>|boq:<id>&right=...`, plus an `.xlsx` export using the existing `openpyxl` dependency and the existing PDF export path (`pdf_export.py`).
- Event-bus subscribers: auto-snapshot on `boq.locked`, `boq.revision_created` and tender/export events. Add a retention setting.
- Validation rule `boq_quality.revision_delta`, a WARNING when the total or any single position moves by more than a configurable percentage without a comment.
- Frontend: a `BOQCompareView` with side-by-side or unified mode, colour-coded rows, a filter for "changed only", and i18n keys. Reuse `VersionHistoryDrawer` to choose the two sides.
- "Create change order from diff" button that posts the changed lines to `changeorders`.

## Building blocks (free/open-source libs, APIs, MCP servers)
- **DeepDiff** (Python), recursive diff of dicts and lists with ignore-order and numeric tolerance. MIT, though one index lists "other", so check the LICENSE file. https://github.com/seperman/deepdiff
- **nested-diff** (Python), a diff and patch alternative. Apache-2.0. https://pypi.org/project/nested-diff
- **jsondiffpatch** (JS), delta format plus an HTML visual formatter, useful for a raw "metadata changed" view. MIT. https://github.com/benjamine/jsondiffpatch
- **SQLAlchemy-Continuum**, row-level audit/version tables. BSD-3-Clause. It would be overkill here because JSON snapshots already exist, but it's an option for per-field history. https://github.com/kvesteri/sqlalchemy-continuum
- **openpyxl** is already a dependency, for exporting the diff to Excel.
- **MCP servers:** I found no dedicated MCP server for BOQ or estimate diffing and could not verify one. The natural route is to expose `compare` as an `erp_chat` tool, so the user can ask "what changed since the client version?".

## Priority: 4/5 — most of the plumbing already exists; a position-level diff, auto-snapshots and an exportable compare report give every estimator high value for little effort
## Sources
- https://github.com/seperman/deepdiff
- https://libraries.io/pypi/deepdiff
- https://pypi.org/project/nested-diff
- https://github.com/benjamine/jsondiffpatch
- https://github.com/kvesteri/sqlalchemy-continuum
- https://pypi.org/project/SQLAlchemy-Continuum
