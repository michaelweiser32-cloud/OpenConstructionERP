# 045. Drawing Management: Sheet Register, Revision Tracking, Auto Sheet-Number Detection, Overlay/Compare

## What it does
You upload a multi-page drawing set (PDF, plus DWG/DXF where available). The system then:
- splits it into individual sheets;
- reads the sheet number, title, revision and scale from the title block;
- files each sheet under its discipline (A/S/M/E/P...);
- matches new uploads against existing sheet numbers, so a re-issued sheet becomes a new revision and the old one is marked superseded;
- lets the user overlay two revisions (old in red, new in blue, unchanged in grey) or view them side by side, so changes in scope show up before the estimate or tender is updated.

Commercial reference points:
- Procore uses OCR on the title block to fill in number, title and discipline. It recognises a duplicate number as a revision and offers compare and bulk compare.
- Fieldwire Sheet Compare (paid plans) overlays the two sheets in red and blue, but only for sheets with the same dimensions.
- Autodesk Build and Trimble Viewpoint offer similar sheet-compare tools.

## Already in the codebase (with file paths)
- `backend/app/modules/documents/models.py`: `Sheet` model (`oe_documents_sheet`) with `sheet_number`, `sheet_title`, `discipline`, `revision`, `revision_date` and `previous_version_id`. `Document` also has `drawing_number`, `revision_code` and `is_current_revision`.
- `backend/app/modules/documents/service.py`:
  - `split_pdf_to_sheets()` splits a PDF into sheets.
  - `detect_sheet_info()` reads number, title, scale and revision with regex on extracted text.
  - `detect_discipline_from_sheet_number()` sets the discipline from the number's letter prefix.
- `backend/app/modules/documents/repository.py`: `get_version_chain()` follows `previous_version_id` links.
- `backend/app/modules/documents/router.py`: endpoints `/sheets/`, `/sheets/split-pdf/`, `/sheets/{id}/versions/` and `/sheets/disciplines/`.
- `backend/app/modules/cde/models.py`: `DocumentContainer` and `DocumentRevision` (ISO 19650-style revision codes and states).
- `backend/app/modules/dwg_takeoff/models.py`: `DwgDrawing.sheet_number` and `DwgDrawingVersion`. Sheet strip UI is in `frontend/src/features/dwg-takeoff/components/SheetStrip.tsx`.
- Dependencies already present: `pymupdf`, `pdfplumber`, `opencv-python-headless` and `paddleocr` (backend), and `pdfjs-dist` (frontend).

**Gap:**
1. Nothing sets `previous_version_id` automatically. A new upload is not matched to an existing sheet by number, so the version chain stays empty unless someone edits it by hand.
2. No frontend page calls the `/sheets` API, so there is no sheet register UI.
3. Detection runs regex over the whole page text. Patterns such as `\b[A-Z]\d{3,4}\b` will also match grid or room labels. There is no title-block region weighting and no OCR fallback for scanned PDFs.
4. There is no overlay or compare feature anywhere, in either PDF or DXF.
5. Nothing links a superseded sheet to the takeoff measurements or BOQ positions that were derived from it.

## Who it helps and how much
- **Small estimators and GCs:** High value. Re-issued drawings are the main cause of missed scope in bids and change orders. Overlay compare cuts revision review from hours to minutes and flags which takeoffs need re-measuring.
- **Site and field users:** Medium value. They need confidence that they are working from the current sheet.
- **Positioning:** This is table stakes in Procore, Fieldwire and ACC, so not having it is a visible gap.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Most of the work is in the `documents` module, with small hooks into `takeoff`, `dwg_takeoff` and `cde`.
1. **Detection v2.** Use PyMuPDF `page.get_text("words")` and score candidates by position (bottom-right title block), by nearby labels ("SHEET NO", "DWG NO", "Blatt", "Plan-Nr.") and by a project-configurable regex. Fall back to PaddleOCR on a crop of the title-block region. Also offer "get from filename". Return a confidence score so the user confirms before saving (AI-augmented, human-confirmed).
2. **Revision matching.** On split, look up the project's current sheet with the same normalised number. Set `previous_version_id` on the new sheet and mark the old one superseded. Publish a `documents.sheet.revised` event.
3. **Compare service.** Rasterise both pages with PyMuPDF at the same DPI and align them with OpenCV `findTransformECC` (affine). Then produce a red/blue/grey composite and a change-region bounding-box list. For vector PDFs, an optional mode diffs the drawing primitives from `page.get_drawings()`.
4. **Frontend.** Add a sheet register grid (filter by discipline, current/superseded, revision history) and a compare viewer built on pdfjs-dist with opacity and swipe controls.
5. **Validation.** Add rules for duplicate sheet numbers, a missing revision, and takeoff linked to a superseded sheet.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **PyMuPDF** for text with coordinates, rasterising and vector drawings. AGPL-3.0 or commercial; already a dependency and compatible with the project's AGPL licence. https://pypi.org/project/PyMuPDF/
- **OpenCV** `findTransformECC` for aligning images before the overlay. Apache-2.0; already a dependency. https://docs.opencv.org/4.1.0/dd/d93/samples_2cpp_2image_alignment_8cpp-example.html
- **PaddleOCR** as the OCR fallback for scanned title blocks. Apache-2.0; already a dependency.
- **PDF.js** for client-side rendering in the compare viewer. Apache-2.0. https://github.com/mozilla/pdf.js
- **Reference visual-diff tools:**
  - diff-pdf (GPL-2.0, CLI): https://github.com/vslavik/diff-pdf
  - diff-pdf-visually (Apache-2.0 listed; confirm in the repo): https://github.com/bgeron/diff-pdf-visually
  - pdf-visual-diff (MIT, npm)
- **MCP servers:** No official Procore or Autodesk MCP server for sheets could be verified. Community servers exist and could serve as optional importers, but should be treated as unvetted:
  - Autodesk Build MCP: https://glama.ai/mcp/servers/@SamuraiBuddha/mcp-autodesk-build
  - Procore MCP: https://glama.ai/mcp/servers/TylerIlunga/procore-mcp-server/schema

  This feature does not need any MCP server.

## Priority: 4/5 — Most of the backend already exists. Auto revision matching and overlay compare can be built with libraries that are already dependencies, and they directly prevent missed scope on re-issued drawings.

## Sources
- https://en-au.support.procore.com/faq/which-fields-can-procore-automatically-populate-when-uploading-drawings
- https://v2.support.procore.com/product-manuals/drawings-project/tutorials/upload-drawing-revisions
- https://support.procore.com/u/andres/Roles/Architect/Tutorials/How_to_improve_the_accuracy_of_OCR
- https://help.fieldwire.com/hc/en-us/articles/115000652623
- https://help.autodesk.com/cloudhelp/ENU/Build-Sheets/files/Compare_Sheets.html
- https://help.trimble.com/doc/viewpoint-team/viewpoint-team/project-management/drawings/compare-drawing-revisions-or-sheets
- https://pypi.org/project/PyMuPDF/
- https://docs.opencv.org/4.1.0/dd/d93/samples_2cpp_2image_alignment_8cpp-example.html
- https://github.com/mozilla/pdf.js
- https://github.com/vslavik/diff-pdf
- https://glama.ai/mcp/servers/@SamuraiBuddha/mcp-autodesk-build
- https://glama.ai/mcp/servers/TylerIlunga/procore-mcp-server/schema
