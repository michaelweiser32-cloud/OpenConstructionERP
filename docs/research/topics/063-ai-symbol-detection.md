# 063. AI Symbol Detection and Auto-Count on Drawings

## What it does
The user clicks one example of a symbol on a plan, such as a door swing, a duplex outlet, a light fixture or a WC. The system then finds every matching instance across a page or a whole drawing set, counts them per sheet, zone or layer, and proposes a count line with a confidence score. The estimator reviews the hits on an overlay, accepts or rejects them, and links the accepted count to a BOQ position. Commercial takeoff tools sell this as "Auto Count" (Kreo, PlanSwift, Countfire, Togal.AI).

## Already in the codebase (with file paths)
- **Manual count tool.** `frontend/src/modules/pdf-takeoff/TakeoffViewerModule.tsx` has a `'count'` measure tool for placing pins by hand. Measurements persist through `backend/app/modules/takeoff/router.py` (`/measurements/`, `/measurements/{id}/link-to-boq/`).
- **Advertised but not built.** The landing copy in the same TSX file promises "Auto symbol detection", and `backend/app/core/marketplace.py` lists a "PDF Takeoff Engine" (`converter-pdf-ocr`) "with symbol detection". No detection endpoint, model or service exists. `services/cv-pipeline/` from CLAUDE.md is not in the repo.
- **Dependencies already declared.** The optional `cv` extra in `backend/pyproject.toml` includes `ultralytics`, `paddleocr`, `opencv-python-headless` and `pymupdf`, but none of them is imported in `backend/app`.
- **CAD block data already parsed.** `backend/app/modules/dwg_takeoff/dxf_processor.py` already extracts `INSERT` entities with `block_name` through ezdxf. Counting doors and outlets in DWG/DXF is therefore a group-by on block name and layer, with no AI needed.

**Gap:** there is no backend detection at all, only manual pins, and the marketplace and UI make claims that are currently unfulfilled.

## Who it helps and how much
Counting is the most tedious part of takeoff for electrical, plumbing, HVAC, fire and door/hardware trades and for GCs pricing fit-out. A small firm often counts hundreds of symbols per bid by hand. Reliable auto-count turns hours into minutes and cuts missed items. Value is **high** for trade subcontractors and small GCs bidding from PDF sets, and medium for firms that mostly receive native CAD, where block counting already covers the need.

## Implementation effort
**Medium** for a useful version and **Large** for a trained ML detector. Staged plan:
1. **DXF/DWG block count (S).** Add `/dwg_takeoff/block-counts/`, which groups `INSERT` entities by block name and layer and returns counts as proposed measurements.
2. **Vector PDF match (M).** Use PyMuPDF `get_drawings()` to extract vector paths and match the selected symbol's path signature, which is rotation- and scale-normalised, across pages.
3. **Raster template match (M).** Use OpenCV `matchTemplate` with multi-scale and rotation search for scanned sheets, plus non-max suppression.
4. **Learned detector (L).** Fine-tune an Apache-2.0 detector (RF-DETR) on FloorPlanCAD-style data for few-shot symbol classes.

The work plugs in as a new `takeoff` endpoint, `POST /takeoff/documents/{id}/detect-symbols/` (an exemplar bbox in, candidate boxes plus confidence out), run as a background task. Results are stored as `source="ai_takeoff"` measurements with `pending` status and never auto-applied (CLAUDE.md principle 7). The frontend overlay shows green, yellow and red confidence with bulk accept/reject. A validation rule such as `takeoff.ai_count_unreviewed` blocks BOQ linkage until the hits are reviewed. Heavy models stay behind the optional `cv` extra so the 2GB-VPS core is unaffected.

**Licensing note:** Ultralytics YOLO is AGPL-3.0, and Ultralytics states that custom-trained models inherit AGPL. That works for the AGPL community edition but conflicts with the planned commercial/enterprise edition. Prefer RF-DETR (Apache 2.0) or classical OpenCV matching.

## Building blocks
- ezdxf: block/INSERT counting. MIT. https://ezdxf.mozman.at/
- PyMuPDF: vector path extraction (`get_drawings`). AGPL-3.0 or commercial license from Artifex. https://pymupdf.readthedocs.io/
- OpenCV `matchTemplate`: Apache 2.0. https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
- RF-DETR detector: Apache 2.0 for the core models. Larger "Plus" variants may use a different license, so verify. https://github.com/roboflow/rf-detr
- Ultralytics YOLO: AGPL-3.0 or paid Enterprise license. https://www.ultralytics.com/license
- FloorPlanCAD dataset: 15k+ vector floor plans, 35 symbol categories, research use. https://floorplancad.github.io/
- Roboflow MCP server: an official hosted MCP server for dataset and model workflows. It is a cloud service with OAuth and is useful for labelling and training experiments, not as a runtime dependency. https://docs.roboflow.com/developer/mcp-server
- I could not verify any MCP server built specifically for construction symbol counting.

## Priority: 4/5
It is a top time-saver that small estimators pay for in competing tools, and the UI already advertises it. The block-count and template-match stages are cheap wins on existing dependencies.

## Sources
- https://www.kreo.net/construction-takeoff-software
- https://www.countfire.com/product/takeoff-software.html
- https://www.bluebeam.com/resources/pdf-markup-for-estimators-2026-guide/
- https://www.ultralytics.com/license
- https://www.ultralytics.com/legal/agpl-3-0-software-license
- https://github.com/roboflow/rf-detr
- https://blog.roboflow.com/rf-detr-is-free-to-use-commercially/
- https://floorplancad.github.io/
- https://arxiv.org/abs/2105.07147
- https://docs.roboflow.com/developer/mcp-server
- https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
- https://ezdxf.mozman.at/
