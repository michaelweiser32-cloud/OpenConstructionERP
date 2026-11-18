# 061. OCR of Drawings: Title Blocks, Sheet Numbers, Dimension Strings, Room Labels

## What it does
It reads the text on construction drawing sets, including scanned or rasterised PDFs and photos, and turns it into structured data:
- **Title block fields**: sheet number, sheet title, scale, revision, date and discipline. These are used to name, index and version sheets automatically, much like Bluebeam's "page labels from page region".
- **Dimension strings** (`3.60`, `12'-6"`): used to calibrate scale and cross-check takeoff measurements.
- **Room labels and tags** (room name and number, area tags, door and window marks): used to seed rooms or zones and count tagged items for the BOQ.

The output is always a suggestion with a confidence score that a person reviews. This follows the project's "AI-augmented, human-confirmed" principle.

## Already in the codebase (with file paths)
- `backend/app/modules/documents/service.py`
  - `split_pdf_to_sheets()` splits uploaded PDFs into `Sheet` records using **pdfplumber text extraction only**.
  - `detect_sheet_info()` uses regex to find the sheet number, title, scale and revision in that text. Its own docstring says it "does NOT rely on external OCR services".
  - `detect_discipline_from_sheet_number()` maps prefixes such as A, S and M to disciplines.
- `backend/app/modules/documents/models.py` has a `Sheet` model with the fields `sheet_number`, `sheet_title`, `discipline`, `revision` and `scale`.
- `backend/pyproject.toml` has an optional `cv` extra that already declares `paddleocr`, `ultralytics`, `opencv-python-headless` and `pymupdf`. However, **no code imports PaddleOCR**, so the dependency is declared but never wired in.
- `backend/app/modules/ai/router.py` sends images to an LLM vision model to extract BOQ data. This is generic and does not handle drawing-specific fields.
- `frontend/src/modules/pdf-takeoff/` contains a viewer and measurement persistence, but no OCR overlay.

**Gaps:**
1. Scanned or raster PDFs give empty text, so every field ends up null.
2. Text is not restricted to the title-block region, so the regex can pick up any `A-101` anywhere on the page and produce false positives.
3. Dimension strings and room labels are not extracted at all.
4. Text positions (bounding boxes) are not stored, so the UI cannot link a result back to its location on the sheet.

## Who it helps and how much
Small estimating firms mostly receive drawing sets as PDFs, many of them scanned or flattened. Today someone renames and indexes 50–300 sheets by hand for each bid, which takes hours per tender. Automatic sheet naming and revision detection is a widely expected feature: Bluebeam's OCR and page-label workflow is the de-facto reference. Extracting room labels and tags is a valuable step towards counting takeoff and room schedules. **Value: High for title blocks and sheet numbers; Medium for dimensions and room labels**, because those are noisier and need review.

## Implementation effort
**Medium** overall. It touches the `documents` module (sheets) and `takeoff`/`pdf-takeoff`, and could later become a `services/cv-pipeline` service.
1. **Small first step**: in `split_pdf_to_sheets()`, when a page has fewer than about 20 characters of text, render it with PyMuPDF and OCR it with PaddleOCR (or Tesseract), behind the optional `cv` extra. If neither is installed, fall back gracefully to the current behaviour.
2. **Title-block zoning**: let a user draw a title-block region once per drawing set, then reuse it for every page (like Bluebeam page regions). As a default, use the bottom-right quadrant. Store the region and the per-field bounding boxes and confidence in the `Sheet` metadata.
3. **Dimension strings and room labels**: run OCR to get text and boxes, then classify each item with regex and heuristics (units, feet/inch patterns, room-number formats). Show the results as an overlay in the takeoff viewer for the user to accept or reject.
4. **Validation**: add rules such as duplicate sheet number, missing revision, and scale that does not match the calibrated dimension (for example in `core/validation/rules`).
5. Run heavy OCR as a background task, using Celery or in-process workers in development, so uploads do not block.

## Building blocks
- **PaddleOCR 3.x** (PP-OCRv5, PP-StructureV3 with coordinates, PaddleOCR-VL): Apache-2.0, free, runs offline. The repo includes an `mcp_server` folder. https://github.com/PaddlePaddle/PaddleOCR
- **Tesseract**: Apache-2.0, lightweight and suited to CPU-only VPS deployments. https://github.com/tesseract-ocr/tesseract
- **docTR (Mindee)**: Apache-2.0 OCR built on PyTorch. https://github.com/mindee/doctr
- **PyMuPDF**: AGPL or commercial licence, which is compatible with this AGPL project. It renders pages and has a Tesseract OCR hook. https://pymupdf.readthedocs.io/
- **Azure Document Intelligence Read**: paid cloud option. Third-party sources cite about $1.50 per 1,000 pages; check the official page before relying on it. https://azure.microsoft.com/pricing/details/document-intelligence/
- **MCP servers**:
  - PaddleOCR ships an MCP server inside its repo. I could not confirm the exact package name.
  - Community Tesseract MCP: `rjn32s/mcp-ocr` (MIT). https://glama.ai/mcp/servers/@rjn32s/mcp-ocr
  - These are useful for the `erp_chat` and AI agents, but the in-process library is simpler for the core pipeline.
- I found **no open-source library made specifically for parsing construction title blocks**. That layer has to be built from regex rules plus user-defined regions.

## Priority: 4/5 — The scaffolding exists (Sheet model, regex, cv extra), so adding an OCR fallback and title-block regions is a cheap, visible win; dimensions and room labels can follow later.

## Sources
- https://github.com/PaddlePaddle/PaddleOCR
- https://github.com/tesseract-ocr/tesseract
- https://github.com/mindee/doctr
- https://pymupdf.readthedocs.io/
- https://support.bluebeam.com/revu/how-to/save-time-with-ocr-and-batch-link.html
- https://azure.microsoft.com/pricing/details/document-intelligence/
- https://glama.ai/mcp/servers/@rjn32s/mcp-ocr
