# 058. Inspections and QA/QC Checklists (templates, pass/fail, NCR linkage)

## What it does
Lets a site team run repeatable quality inspections (pre-pour, rebar, waterproofing, MEP rough-in, handover) from **reusable checklist templates**. Each item gets a pass / fail / N/A answer, with photos, notes and a sign-off. A failed item can create a **punch item (defect)** or a **Non-Conformance Report (NCR)** with one click. Corrective action is then tracked until closure and re-inspection.

## Already in the codebase (with file paths)
- `backend/app/modules/inspections/` has a full CRUD module.
  - Model `QualityInspection` in `models.py` has type, location, WBS, inspector, a status workflow (`scheduled -> in_progress -> completed/failed`, with re-inspection allowed), a `result` of pass/fail/partial, and a free-form JSON `checklist_data`.
  - `service.py` validates checklist structure, with response types `yes_no`, `pass_fail`, `numeric`, `text` and `rating`.
  - `router.py` has an Excel export with a pass/fail count, `/complete/`, and `/{id}/create-defect/`. That endpoint creates a `PunchItem` from the failed checklist items through a lazy import of `punchlist`.
- `backend/app/modules/ncr/` has an NCR model with root cause, corrective and preventive action, cost and schedule impact, `linked_inspection_id` and `change_order_id`.
- `backend/app/modules/punchlist/` is the defect list.
- Frontend: `frontend/src/features/inspections/InspectionsPage.tsx` (create defect, link to `/ncr`), plus `features/ncr` and `features/punchlist`.

**Gaps:**
1. There is **no template entity**. Checklists are retyped per inspection and there is no company or regional template library.
2. There is **no "create NCR from failed inspection" endpoint**. The NCR link is a manual string field with no FK.
3. There are no per-item photos or signatures, no hold/witness points, and nothing ties the module to ITPs (Inspection and Test Plans).
4. No event such as `inspection.failed` is published for notifications or workflow.
5. There is no validation rule set for QA, such as "NCR open > X days" or "inspection failed without a follow-up".
6. There is no offline or mobile-first execution.

## Who it helps and how much
- **Small general contractors and subcontractors (high value):** they replace paper and Excel checklists, prove quality to clients and reduce rework disputes. Failed item -> defect/NCR -> change order is a direct cost-recovery path.
- **Estimators (medium value):** NCR cost-impact data feeds back into contingencies.
- **Site supervisors (high value):** template reuse saves time on every inspection.

## Implementation effort
**Medium.** The modules touched are `inspections`, `ncr`, `punchlist`, `notifications`, `validation` and the regional packs.
- Add an `InspectionTemplate` model to the `inspections` module: name, trade, standard tag, a versioned `items` JSON with the same schema `_validate_checklist_structure` already enforces, and a `hold_point` flag. Instantiate it with `POST /inspections/from-template/{id}`.
- Seed starter templates through the regional packs (`dach_pack`, `uk_pack`, `us_pack`) as JSON. That keeps the manifest/plugin philosophy: a new template pack is just a file.
- Add `POST /inspections/{id}/create-ncr/`, mirroring `create-defect`. Store the back-link in the NCR's `linked_inspection_id`, and add an optional `ncr_id` and `punch_item_id` to each checklist item.
- Publish `inspections.inspection.failed` and `ncr.created` on the core event bus, so `notifications` and the integrations (Slack, Teams, email) can subscribe.
- Add validation rules (`qa_open_ncr_age`, `qa_failed_without_action`, `qa_hold_point_unreleased`) in the validation module. That follows the "no module without validation" rule.
- Expose checklist and NCR tools in `erp_chat/tools.py`, such as "list open NCRs" and "draft an NCR from inspection X". Drafts are AI-suggested and human-confirmed.
- Frontend: add a template picker, a mobile-friendly runner (photo capture through the existing `documents`/storage layer) and a status badge for the NCR link.

## Building blocks
- **SurveyJS Form Library**: renders JSON-defined checklists in React. The core library is MIT; the Survey Creator visual builder is commercial. A hand-rolled React form is simpler and lighter. https://github.com/surveyjs/survey-library, https://surveyjs.io/Licenses
- **Procore Inspections/Checklist REST API**: a reference model for template -> list -> item -> observation, and a source for a possible import connector. It requires a paid Procore account and an OAuth app. https://developers.procore.com/reference/rest/checklist-comments
- **SafetyCulture (iAuditor) API**: a popular inspection app with an import source for templates and inspections. Third-party sources say API access needs the Premium tier (about $24-29 per user per month) and that the free tier is limited to 5 active templates. I could not open its official developer site (developer.safetyculture.io) from this session because the host was not allowed. https://www.g2.com/products/safetyculture-iauditor/pricing
- **MCP**: there is a community `safetyculture-mcp-server`, which reads the SafetyCulture Feed API. It is unofficial and has not been audited. https://github.com/zerubroberts/safetyculture-mcp-server. Composio also hosts a SafetyCulture toolkit: https://composio.dev/toolkits/safetyculture/framework/autogen.md. **I found no official Procore MCP server.** OpenConstructionERP's own MCP and erp_chat tools are the better route.
- **openpyxl** (already used for export, MIT/BSD-style) can import Excel checklists into templates.

## Priority: 4/5 — the module exists, so templates and NCR auto-linking are cheap, high-frequency wins for small contractors
The inspections, NCR and punchlist modules are already in place. The remaining work is a template library, a one-click NCR, events and QA validation rules. That turns isolated CRUD into a closed quality loop that every small contractor uses weekly. Building third-party connectors to SafetyCulture or Procore can wait.

## Sources
- https://github.com/surveyjs/survey-library
- https://surveyjs.io/Licenses
- https://developers.procore.com/reference/rest/checklist-comments
- https://support.procore.com/faq/inspection-requirements-general-faq
- https://hexdocs.pm/procore_sdk/Procore.Api.QualitySafetyInspectionsCompanyInspectionTemplateItems.html
- https://www.g2.com/products/safetyculture-iauditor/pricing
- https://github.com/zerubroberts/safetyculture-mcp-server
- https://glama.ai/mcp/servers/zerubroberts/safetyculture-mcp-server
- https://composio.dev/toolkits/safetyculture/framework/autogen.md
