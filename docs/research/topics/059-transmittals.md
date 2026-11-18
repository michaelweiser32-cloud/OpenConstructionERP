# 059. Transmittals and document control (ISO 19650 states, issue sheets)

## What it does
Document control is the record of which drawing or document went to whom, at which revision, with which status, and why. ISO 19650 adds a Common Data Environment (CDE) lifecycle (WIP -> Shared -> Published -> Archived), suitability codes (S0-S7, A1-A5) and a structured file-naming convention. The UK National Annex (2021) names the fields Project-Originator-Functional-Spatial-Form-Discipline-Number, with status and revision such as `S2-P01` added after the number. The paper trail consists of the **transmittal**, a cover sheet listing the documents sent, and the **drawing issue sheet** (drawing register), a matrix with one row per drawing and one column per issue date that shows the revision and suitability on each issue. For a small contractor or estimator, this shows which drawing revision a bid or BOQ was priced from. That is the starting point for most claims and change-order disputes.

## Already in the codebase (with file paths)
The data model is mostly built.
- `backend/app/modules/cde/` has ISO 19650 containers with naming fields: `originator_code`, `functional_breakdown`, `spatial_breakdown`, `form_code`, `discipline_code`, `sequence_number` and `suitability_code` (`models.py`). It also has revisions and a state-transition audit log with gate approval and an approver signature (`service.py`).
- `backend/app/core/cde_states.py` holds `CDEStateMachine`, which handles allowed transitions and role gates.
- `backend/app/modules/cde/suitability.py` is the ISO 19650-1 suitability-code table plus a check that the code fits the state.
- `backend/app/modules/transmittals/` covers transmittals with a purpose code, recipients (acknowledge and respond) and items linked to `document_id`/`revision_id`. It supports draft, then issue, then lock.
- `frontend/src/features/transmittals/TransmittalsPage.tsx` and `frontend/src/features/cde/` provide the UI.
- `reportlab` is already a dependency (`backend/pyproject.toml`, used in `backend/app/modules/boq/pdf_export.py`).

**Gaps**
- No PDF output for a transmittal cover sheet or a drawing issue sheet.
- No cross-transmittal "drawing register" matrix.
- No validation of `container_code` against a project naming convention.
- No email distribution with acknowledgement links on issue.
- No event when a transmittal is issued (it could flag BOQ items priced from superseded revisions).
- No bulk upload that parses metadata from file names.

## Who it helps and how much
Subcontractors and estimators get proof of the drawing set each price was based on. They can also see straight away when a new revision makes part of an estimate out of date. Small GCs and design-build firms get audit-ready issue records without paying for an enterprise CDE. UK and EU firms on public work often have ISO 19650 compliance written into the contract. The value is Medium-High: this is unglamorous work, but it protects margin in variation disputes.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Small-Medium.** The work stays inside the existing `transmittals` and `cde` modules, and no new module is needed.
1. Add `transmittals/pdf_export.py` with ReportLab, reusing the BOQ PDF style. Expose `GET /transmittals/{id}/pdf` and `GET /transmittals/register/pdf?project_id=` for the issue-sheet matrix, built from items joined to CDE revisions.
2. Publish a `transmittals.issued` event on the core event bus. A `boq` hook subscribes to it and marks positions linked to superseded revisions with a validation WARNING.
3. Add a validation rule, `iso19650.naming_convention`, under `backend/app/core/validation/rules/`. It uses a per-project configurable field pattern stored in ProjectConfig.
4. Send recipient notifications through the existing `notifications` and `integrations/email` modules, using signed acknowledge links.
5. Optionally add `erp_chat/tools.py` tools such as "list documents issued to X since date" and "which revision was the bid based on".

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- ReportLab: https://www.reportlab.com/opensource/ (BSD). Already a dependency here, so it covers the PDF sheets.
- Autodesk ACC Transmittals API: https://aps.autodesk.com/en/docs/acc/v1/reference/http/transmittals-listtransmittals-GET/. Documented and read-only. Access needs an APS app plus an ACC subscription on the customer side, and it could import transmittals from ACC.
- Official APS MCP server example: https://github.com/autodesk-platform-services/aps-mcp-server-nodejs (license not checked). It reads ACC folders and documents.
- Community Procore MCP servers, for example https://github.com/TylerIlunga/procore-mcp-server. These are unofficial, and their license and maintenance were not checked. Procore has a transmittals tool (https://support.procore.com/products/online/user-guide/project-level/transmittals), but I could not confirm a public transmittals REST endpoint.
- Reference implementation: https://github.com/mohammadgulab/doc-register-api, a small register/transmittal REST API with CSV export. It is useful for comparing features, not as a dependency, and its license was not checked.
- Naming-convention references: https://www.symetri.co.uk/insights/blog/iso-19650-file-naming-update/ and https://bimleed.com/blog/iso-19650-file-naming-and-status-codes.

## Priority: 3/5 — the core models already exist, so issue-sheet PDFs, naming validation and the stale-revision BOQ warning are cheap and high-trust additions, but they are not what drives adoption for small estimators
Lower than estimating features because the main data model is already done. Higher than nice-to-haves because these additions are cheap and support claims defence.

## Sources
- https://www.symetri.co.uk/insights/blog/iso-19650-file-naming-update/
- https://bimleed.com/blog/iso-19650-file-naming-and-status-codes
- https://www.bi3m.com/knowledge/bim-and-digital-engineering-insights/iso-19650/naming-and-information-structure
- https://aps.autodesk.com/en/docs/acc/v1/reference/http/transmittals-listtransmittals-GET/
- https://autodesk-platform-services.github.io/aps-mcp-server-nodejs/
- https://github.com/TylerIlunga/procore-mcp-server
- https://support.procore.com/products/online/user-guide/project-level/transmittals
- https://github.com/mohammadgulab/doc-register-api
- https://www.atelierlab.in/articles/drawing-issue-register-transmittal-architects
- https://www.reportlab.com/opensource/
