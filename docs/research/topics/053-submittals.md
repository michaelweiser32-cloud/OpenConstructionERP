# 053. Submittal workflow (register from specs, review stamps, resubmittals)

## What it does
A submittal workflow tracks the shop drawings, product data, samples and certificates a contractor must send for review before buying or installing anything. A full workflow has three parts:
- **Register from specs**: parse the project specification (for example the MasterFormat "PART 1 - SUBMITTALS" articles) and generate a draft log with one row per required item, each carrying its spec section, type and due date.
- **Review stamps**: the reviewer returns the PDF stamped with a disposition ("Approved", "Approved as Noted", "Revise and Resubmit", "Rejected"), plus a reviewer name, date and comments.
- **Resubmittals**: each revision keeps its own documents, comments and dates (Rev 0, Rev 1, ...), and the register shows ball-in-court and days outstanding.

## Already in the codebase (with file paths)
- `backend/app/modules/submittals/models.py`: the `Submittal` model has `spec_section`, `submittal_type`, `status`, `ball_in_court`, `current_revision` (an integer only), reviewer/approver, submitted/required/returned dates, and `linked_boq_item_ids`.
- `backend/app/modules/submittals/service.py`: a status state machine (`_SUBMITTAL_STATUS_TRANSITIONS`) with draft, submitted, under_review, approved, approved_as_noted, revise_and_resubmit, rejected and closed. `submit` increments `current_revision` on a resubmission, and events are published.
- `backend/app/modules/submittals/router.py`: CRUD plus submit, review and approve endpoints, and attachments linked to `documents`.
- `backend/app/modules/markups/models.py`: a `StampTemplate` exists for markups, but it is not wired into submittal dispositions.
- `frontend/src/features/submittals/SubmittalsPage.tsx`: the list and detail UI. `erp_chat/tools.py` already references submittals.

**Gap:**
- There is no per-revision history table. Comments, attachments and the disposition for each revision are overwritten.
- There is no spec-book parser to generate a register.
- No burned-in review stamp is written onto the returned PDF.
- There is no lead-time or required-on-site scheduling, and no link to `schedule` activities.
- There are no validation rules for submittals (for example "overdue", "missing spec section", "approved without attachment").

## Who it helps and how much
- **Small GCs and specialty subcontractors** spend hours building submittal logs by hand from spec books. Procore markets its Submittal Builder as turning that into "minutes", which shows the demand.
- **Small architects and engineers** who review submittals need consistent stamps and an audit trail.
- **Estimators** gain from the existing BOQ link: approved products confirm the priced items.

The value is High for GCs and subcontractors on spec-driven (US, UK, commercial) work, and Low for small residential builders who rarely receive formal spec books.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
Medium overall, built in three pieces:
1. **Revisions (Small)**: add a `SubmittalRevision` model (revision number, attachments, disposition, reviewer comments, dates) and a module-scoped Alembic migration. `submit` and `review` then write revision rows. Validation rules (`submittals.overdue`, `submittals.no_spec_section`) are registered with the core validation engine.
2. **Stamps (Small)**: on `review`, render the disposition from a `markups` StampTemplate onto a copy of the PDF. The copy is stored via `core/storage` as a new `documents` version. All stamp labels go through i18n.
3. **Register from specs (Medium)**: an upload endpoint extracts text per page and detects section headers (`SECTION 03 30 00`) and SUBMITTALS articles with regex. An optional `ai` module LLM pass classifies the items, each with a confidence score. Draft rows go to a review screen that a human confirms (AI-augmented, human-confirmed). Spec sections link to `schedule` activities to compute "submit by" dates from lead times.

Optional sync to Procore or ACC goes through `integrations` connectors.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **PyMuPDF**: `Page.add_stamp_annot`, text and overlay insertion for burned-in stamps. Dual-licensed AGPL-3.0 or commercial, which is compatible with this AGPL project. https://github.com/pymupdf/pymupdf
- **pdfplumber**: page text extraction for parsing spec books. MIT license. https://github.com/jsvine/pdfplumber
- **Autodesk Construction Cloud Submittals API**: official REST API with items, specs, revisions and transitions (`create_revision`). An ACC subscription is required. https://aps.autodesk.com/en/docs/acc/v1/reference/http/submittals-items-GET
- **Procore Submittals API**: the reference for the register-from-spec UX (Submittal Builder). A paid Procore account is required. https://support.procore.com/products/online/user-guide/project-level/specifications/tutorials/generate-submittal-log
- **MCP servers (community, not official)**:
  - `TylerIlunga/procore-mcp-server` (TypeScript) exposes list/create/update submittal tools: https://github.com/TylerIlunga/procore-mcp-server
  - Community APS/ACC MCP servers that list submittal items are indexed on glama.ai, but I could not verify their repos or licenses.
  - I found no official Procore or Autodesk submittal MCP server.
- **Own MCP exposure**: extending the existing `erp_chat/tools.py` with "list overdue submittals" and "draft register from spec" tools is low effort.

## Priority: 4/5 — the core state machine exists, so revision history, stamps and a spec-to-register parser are a medium-effort, high-visibility upgrade for spec-driven small contractors

## Sources
- https://support.procore.com/products/online/user-guide/project-level/specifications/tutorials/generate-submittal-log
- https://blog.procore.com/introducing-submittal-builder-generate-your-submittal-registries-in-minutes
- https://aps.autodesk.com/en/docs/acc/v1/reference/http/submittals-items-GET
- https://aps.autodesk.com/en/docs/acc/v1/tutorials/submittals/create-submittal-item
- https://aps.autodesk.com/blog/autodesk-construction-cloud-submittals-write-api-and-updates
- https://github.com/pymupdf/pymupdf
- https://artifex.com/blog/working-with-pdf-annotations-in-python
- https://github.com/jsvine/pdfplumber
- https://github.com/TylerIlunga/procore-mcp-server
