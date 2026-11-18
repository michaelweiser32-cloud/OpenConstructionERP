# 060. Closeout, Warranty Tracking and O&M Manual Handover (COBie-like Data)

## What it does
Closeout is the last phase of a project. The contractor collects the handover deliverables (O&M manuals, warranties, as-builts, test certificates, attic stock, training records), puts them together into an indexed handover package, and passes the asset data to the owner, often as a COBie workbook. Warranty tracking carries on after handover. It records when each coverage period starts (usually substantial completion), which trade is responsible and when coverage expires, and it logs warranty callbacks or defects so they can be sent back to the right subcontractor.

## Already in the codebase (with file paths)
- **COBie export:** `backend/app/modules/bim_hub/exporters/cobie.py` builds a COBie UK 2.4 workbook with 7 sheets (Contact, Facility, Floor, Space, Type, Component, System). The route is `GET /models/{model_id}/export/cobie.xlsx` in `backend/app/modules/bim_hub/router.py`. The Document, Job, Spare, Resource and Attribute sheets are left out on purpose.
- **Asset register:** `BIMElement.is_tracked_asset` and `asset_info` hold manufacturer, model, serial and `warranty_until` (`backend/app/modules/bim_hub/models.py`). The `/assets` list and PATCH endpoints feed `frontend/src/features/bim/AssetsPage.tsx` and `AssetEditModal.tsx`.
- **COBie import (requirements side):** `backend/app/modules/bim_requirements/parsers/cobie_parser.py`.
- **Submittal types:** these include `warranty`, `certificate` and `test_report` (`backend/app/modules/submittals/schemas.py`).
- **Related modules:** handover inspections (`inspections/manifest.py`), handover milestones (`projects/models.py`), and the `punchlist`, `documents`, `cde` and `notifications` modules.

**Gap:** there is no closeout module. Missing pieces are:
- a closeout checklist per spec section or subcontractor, with required/received/approved status;
- O&M manual assembly (an indexed, bookmarked PDF built from submittals and documents);
- warranty records that live outside BIM, since most small jobs have no model;
- a warranty start date tied to substantial completion;
- expiry reminders;
- warranty claim/callback logging;
- the COBie Document, Spare and Job sheets.

## Who it helps and how much
- **Small general contractors and fit-out or renovation firms:** this group benefits most. Closeout is usually spreadsheet-and-email work, it holds back retention release and final payment, and lost warranty documents turn into unpaid callbacks.
- **Subcontractors (MEP, roofing):** they get warranty expiry reminders and a callback history.
- **Owners and FM teams:** they get a single handover package plus COBie data for their CAFM.
- **Value:** High for cash flow (retention release) and risk. Most small jobs do not need full COBie, but a "COBie-lite" asset/warranty list in a spreadsheet is commonly asked for.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** The work is a new module `oe_closeout` (`backend/app/modules/closeout/`) with `depends=["oe_projects", "oe_submittals", "oe_documents", "oe_punchlist"]`.
- **Models:**
  - `CloseoutItem`: project, spec section/trade, type (om_manual, warranty, as_built, training, attic_stock), responsible contact, due date, status, linked submittal/document IDs.
  - `Warranty`: item/asset ref, start rule (substantial completion or a fixed date), duration in months, expiry, responsible contact, document link.
  - `WarrantyClaim`: date, issue, status, linked punch item.
- **Service:**
  - auto-generate the checklist from approved submittals of type warranty/certificate;
  - compute expiries from the handover milestone;
  - assemble the O&M package by merging PDFs with pypdf, adding bookmarks and a ReportLab cover/TOC (both libraries already in or compatible with the stack).
- **Events and scheduling:**
  - listen for `submittal.approved` and `milestone.completed`;
  - a periodic task sends `notifications` 90/30 days before a warranty expires.
- **Validation rules:** `closeout.all_required_received` and `closeout.warranty_has_start_date`, which block the "ready for handover" status.
- **COBie integration:** extend `bim_hub/exporters/cobie.py` with Document, Spare and Job sheets sourced from closeout records. Also add a model-free asset/warranty export for projects without BIM.
- **AI integration:** expose read-only tools in `erp_chat/tools.py`: "which warranties expire this quarter", "what closeout items are missing for subcontractor X". AI-extracted warranty terms from PDFs are suggestions that a person confirms.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **NBIMS-US V3 COBie 2.4 Annex A:** the worksheet mapping rules. It is a free public spec (https://nibs.org/wp-content/uploads/2025/04/NBIMS-US_V3_4.2_COBie_Annex_A.pdf). COBie v3 is in draft at buildingSMART.
- **openpyxl:** MIT, already a dependency. Used to write the workbook.
- **pypdf:** BSD-3-Clause (https://pypdf.readthedocs.io/en/latest/meta/faq.html). Used to merge PDFs and add outlines.
- **ReportLab:** BSD open-source edition, already a dependency. Used for the cover and TOC.
- **PyMuPDF:** already in the optional dependencies, but it is AGPL. That fits this project's AGPL-3.0 licence, though it is worth noting.
- **opensourceBIM COBie-plugins:** Java, for BIMserver. The last release is old, so use it only as a reference (https://github.com/opensourceBIM/COBie-plugins).
- **openMAINT:** an AGPL CMMS that a handover could be pushed into through its CSV/webservice interfaces. I could not confirm COBie import (https://www.openmaint.org/en/download/license).
- **MCP:** I found no COBie or warranty MCP server. `cmms-mcp-server` is a demo with no real backend (https://github.com/parissaahmadi/cmms-mcp-server). The official MCP Python SDK can be used to expose closeout tools (https://github.com/modelcontextprotocol/python-sdk).
- **Commercial reference:** Procore has no confirmed native warranty tool. Teams use Submittals/Documents plus marketplace apps such as Closeout Pro (https://marketplace.procore.com/apps/closeout-pro), which shows demand for this feature.

## Priority: 4/5 — closeout holds back retention release and warranty callbacks cost small firms real money; most building blocks (submittals, assets, COBie exporter, notifications) already exist, so a medium-sized module closes a visible gap.

## Sources
- https://nibs.org/wp-content/uploads/2025/04/NBIMS-US_V3_4.2_COBie_Annex_A.pdf
- https://www.buildingsmart.org/wp-content/uploads/2022/11/COBie-v3-Standard_Executive-Summary_DRAFT061322.pdf
- https://en.wikipedia.org/wiki/COBie
- https://www.procore.com/library/construction-closeout-documents
- https://community.procore.com/s/question/0D58V000087GUDsSAO/operations-and-maintenance-manuals
- https://marketplace.procore.com/apps/closeout-pro
- https://warrantyhub.com/blog/procore-warranty-management-closeout/
- https://pypdf.readthedocs.io/en/latest/meta/faq.html
- https://github.com/opensourceBIM/COBie-plugins
- https://www.openmaint.org/en/download/license
- https://github.com/parissaahmadi/cmms-mcp-server
- https://github.com/modelcontextprotocol/python-sdk
