# 062. PDF takeoff: vector-based area/length/count measurement with scale calibration

## What it does
On-screen takeoff measures lengths, areas, perimeters and counts directly on PDF drawings once the sheet scale is known. The **vector-based** part reads the CAD-exported line work inside the PDF (path operators `m`, `l`, `c`, `re`) instead of relying only on pixels. That lets the cursor **snap** to wall corners, line endpoints and intersections, lets the user **one-click fill** a closed room, and lets the tool **read the scale** from the drawing (a scale note like "1:50", or a PDF Measure/Viewport dictionary, ISO 32000 rectilinear `RL` measure) instead of requiring a two-click calibration on every sheet.

## Already in the codebase (with file paths)
A solid manual base already exists, so the gap is "smart vector" features.
- Backend measurement model with types `distance`, `area`, `count`, `polyline` and `volume`, plus `scale_pixels_per_unit`, `perimeter`, `depth` and a BOQ link: `backend/app/modules/takeoff/models.py` (`TakeoffMeasurement`).
- CRUD, bulk create, summary, export and link-to-BOQ operations: `backend/app/modules/takeoff/service.py` and `router.py`.
- PDF text/table extraction with pdfplumber, falling back to PyMuPDF (both already dependencies in `backend/pyproject.toml`). Vector paths (`get_drawings`) are **not** used.
- Frontend viewer on `pdfjs-dist` 4.x: `frontend/src/modules/pdf-takeoff/TakeoffViewerModule.tsx`.
- Two-click calibration and common scale presets: `frontend/src/features/takeoff/components/CalibrationDialog.tsx` and `frontend/src/modules/pdf-takeoff/data/scale-helpers.ts`.
- Undo, groups and a measurement ledger: `frontend/src/features/takeoff/lib/`.
- DWG/DXF takeoff exists separately in `backend/app/modules/dwg_takeoff/`.

**Missing:** snapping to vector geometry, auto-scale detection (scale note text or PDF Measure dictionary), per-sheet or per-viewport scales, one-click room or area fill, cut-outs/deductions (holes in polygons), auto-count of repeated vector symbols, and a validation rule that flags "measured on uncalibrated sheet".

## Who it helps and how much
- Small estimators and subcontractors (drywall, flooring, painting, roofing, concrete) who receive most plans as CAD-exported vector PDFs. Snapping and one-click areas cut clicks heavily and remove calibration mistakes, which are a top cause of takeoff errors.
- Commercial takeoff tools charge roughly USD 2,000 or more per user per year (per review-site listings for PlanSwift and STACK). A free, integrated takeoff-to-BOQ flow is a strong reason for a small firm to adopt the ERP.
- **Value: High.**

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Modules touched: `takeoff` (backend) and `pdf-takeoff` (frontend).
1. Backend: add a `GET /api/v1/takeoff/documents/{id}/pages/{n}/vectors` endpoint. It would use PyMuPDF `page.get_drawings()` to return simplified segments and closed polygons in PDF user space, cached in `TakeoffDocument.page_data`. The same pass would read `/VP` Viewport → `/Measure` dictionaries and regex-scan page text for scale notes, then suggest a scale with a confidence score. The user confirms the suggestion; it is never applied automatically.
2. Frontend: build a snap index (endpoints, midpoints, intersections) in a spatial grid. Add snap indicators and a "fill closed region" tool. Alternatively, extract vectors client-side via pdf.js `getOperatorList()` (`OPS.constructPath`).
3. Geometry: polygon with holes for cut-outs (Shapely, server side), and net area and perimeter.
4. Validation: add a `takeoff_quality` rule set covering uncalibrated sheet, scale mismatch between sheets, and zero-area or duplicate measurements, registered through the core validation engine.
5. Emit a `takeoff.measurement.created` event so BOQ quantities can update through the existing link.
Scanned or raster PDFs still fall back to manual measurement, or to the AI/CV pipeline.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **PyMuPDF `Page.get_drawings()`** returns vector paths as dictionaries. It is AGPL-3.0 or commercial (Artifex), which is compatible with this AGPL project and already a dependency. https://pymupdf.readthedocs.io/en/latest/recipes-drawing-and-graphics.html
- **pdf.js `getOperatorList()`**: client-side path operators, Apache-2.0, already a dependency. Watch out for consecutive `constructPath` batches. https://github.com/mozilla/pdf.js/issues/10522
- **pdfplumber**: `lines`, `rects` and `curves` objects, MIT, already a dependency. https://github.com/jsvine/pdfplumber
- **Shapely**: polygon union, difference and area, BSD-3-Clause. https://github.com/shapely/shapely
- **ISO 32000 Viewport/Measure (rectilinear) dictionaries** for embedded scale. https://pdf-raku.github.io/PDF-ISO_32000-raku/lib/ISO_32000/Table_262-Additional_entries_in_a_rectilinear_measure_dictionary.rakumod
- **OpenTakeoff**: an open-source browser takeoff engine with scale-note reading, corner snapping, cut-outs, and an MCP server (`npx opentakeoff-mcp`, with a `get_sheet_vectors` tool and proposals that a person accepts). Licensed AGPL-3.0 (earlier commits Apache-2.0). It is a useful reference implementation and an MCP option for AI agents. https://github.com/Kentucky-ai/opentakeoff
- **Commercial SDKs with snapping** (Nutrient/PSPDFKit, Apryse): proprietary and paid. They are not recommended, but they show the expected UX. https://www.nutrient.io/sdk/measurement-tools/

## Priority: 5/5 — Core daily workflow for small estimators; the manual base already exists, so vector snapping and auto-scale add large value for medium effort on existing dependencies.

## Sources
- https://pymupdf.readthedocs.io/en/latest/recipes-drawing-and-graphics.html
- https://artifex.com/blog/extracting-and-creating-vector-graphics-in-a-pdf-using-python-pymupdf
- https://github.com/mozilla/pdf.js/issues/10522
- https://dev.to/bonzai2carn/the-three-tier-pdf-extraction-model-demystifying-pdfjs-52bc
- https://pdf-raku.github.io/PDF-ISO_32000-raku/lib/ISO_32000/Table_262-Additional_entries_in_a_rectilinear_measure_dictionary.rakumod
- https://api.itextpdf.com/iText5/java/5.5.13.1/com/itextpdf/text/pdf/spatial/Viewport.html
- https://github.com/Kentucky-ai/opentakeoff
- https://novedge.com/blogs/design-news/bluebeam-tip-enable-snap-to-content-for-faster-more-accurate-takeoffs
- https://www.nutrient.io/sdk/measurement-tools/
- https://us.fitgap.com/search/takeoff-software/contractor?page=1
