# 092. Excel and Google Sheets import/export (round-trip editing, templates)

## What it does
Lets an estimator export a BOQ, cost database or register (RFIs, punch items, contacts) to a spreadsheet, edit it offline or share it with a subcontractor, and re-import it so the platform updates existing rows rather than appending duplicates. "Round-trip" means every exported row carries a stable hidden key (position UUID + version stamp), the re-import shows a diff (changed / new / deleted / conflicting rows) that a human confirms, and the diff passes through the validation pipeline before it is stored. Templates are pre-formatted workbooks (input sheets with dropdowns, locked formula columns, an instructions tab) that customers download, fill in and upload. A Google Sheets connector does the same thing live against a shared Sheet, with no file shuffling.

## Already in the codebase (with file paths)
- Backend dependency `openpyxl>=3.1.0` (`backend/pyproject.toml`).
- BOQ: `export_boq_excel`, `export_boq_csv` and `import_boq_excel` in `backend/app/modules/boq/router.py`. The export keeps custom columns ("survives a round-trip through Excel"). The import maps columns by header aliases (EN/DE) and **creates new positions**. It does not match rows back by ID, and it has no diff/merge or conflict check. `smart_import` and BOQ templates (`list_templates`, `create_boq_from_template`) live in the same file.
- Costs: `/import/file/` and `/actions/export-excel/` in `backend/app/modules/costs/router.py`.
- Ad-hoc Excel exports in many routers: rfi, punchlist, safety, inspections, fieldreports, finance, contacts, tasks, takeoff. Also `bim_requirements/parsers/excel_parser.py` + `exporters/excel_exporter.py`, and `bim_hub/exporters/cobie.py`.
- Frontend: `frontend/src/features/boq/exportExcel.ts` (SheetJS `xlsx` 0.18.5 from npm) and `ExcelPasteModal.tsx` (paste rows from Excel/Sheets).
- Google Sheets: only an `info_only` card in `frontend/src/features/integrations/IntegrationsPage.tsx` ("export as Excel then open in Sheets"). There is no API connector.

**Gap:** keyed round-trip with diff review, one shared export/import framework instead of many per-router copies, downloadable input templates with data validation and protected columns, and a live Google Sheets sync.

## Who it helps and how much
High value for small firms. Spreadsheets are their main tool, and subcontractors and clients send and expect Excel. Round-trip removes re-keying and duplicate positions, which is the biggest adoption barrier when moving off spreadsheets. Google Sheets sync helps teams already on Google Workspace, and it lets a subcontractor price a shared sheet without an account. This is a must-have for onboarding (migrating legacy estimates), not just a nice-to-have.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium overall.** Keyed Excel round-trip is S-M. Google Sheets connector is M.
- New core helper `backend/app/core/spreadsheet/` with a declarative column spec per entity: field, header i18n key, type, editable, enum values. One `export(spec, rows)` writes the hidden `_oe_id` / `_oe_rev` columns, openpyxl `DataValidation` dropdowns (units, classification codes), sheet protection on computed columns, and an i18n instructions sheet. One `parse(spec, file)` returns a `ChangeSet`.
- BOQ, costs and register modules register their specs via a hook, for example `spreadsheet.specs`. Import becomes two steps: `POST .../import/preview` returns the diff plus a ValidationReport (`boq_quality` rules), and `POST .../import/apply` commits it. This follows the "AI/human-confirmed" and "validation always" principles. Revision stamps detect conflicts.
- Optional module `integrations/google_sheets`: OAuth (user) or service account, push a BOQ to a Sheet, pull edits through the same `ChangeSet` preview. Should respect the 60 req/min/user quota by batching (`spreadsheets.values.batchUpdate`).
- Housekeeping: move frontend SheetJS to the SheetJS CDN build (0.20.x) or do exports server-side. The npm 0.18.5 build carries known CVEs, though export-only use is unaffected.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- openpyxl (MIT): read/write xlsx, DataValidation, sheet protection. https://openpyxl.readthedocs.io/
- SheetJS Community Edition (Apache-2.0). Releases after 0.18.5 are only on cdn.sheetjs.com. https://docs.sheetjs.com/docs/getting-started/installation/frameworks
- Google Sheets API v4: free, 300 req/min per project and 60 per user, 429 on overrun, no billing. https://developers.google.com/sheets/api/limits
- gspread (MIT): thin Python Sheets client. https://github.com/burnash/gspread
- MCP: `xing5/mcp-google-sheets` (MIT, Python, about 20 tools, service-account or OAuth). https://github.com/xing5/mcp-google-sheets
- MCP: `taylorwilsdon/google_workspace_mcp` (MIT, Sheets plus Drive/Docs/Gmail). https://github.com/taylorwilsdon/google_workspace_mcp
- No official Google-published Sheets MCP server could be verified. The two above are community projects.

## Priority: 5/5 — spreadsheets are the lingua franca of small estimators; keyed round-trip plus templates removes the main migration barrier at moderate cost on existing openpyxl code.

## Sources
- https://developers.google.com/sheets/api/limits
- https://github.com/xing5/mcp-google-sheets
- https://github.com/taylorwilsdon/google_workspace_mcp
- https://docs.sheetjs.com/docs/getting-started/installation/frameworks
- https://git.sheetjs.com/sheetjs/sheetjs/issues/3012
- https://openpyxl.readthedocs.io/
- https://github.com/burnash/gspread
