# 008. Quantity formulas and measurement sheets

## What it does
This gives each BOQ position a dimension sheet (German *Aufmaß*/*Mengenansatz*, UK "dimension paper"). It holds several rows of `description | count (timesing) | L | W | H | formula | result`, and the position quantity is the sum of those rows. Each row stays traceable: for example "Wall axis A, 2 × 12.50 × 3.00 − door 1.01 × 2.13". The engine supports spreadsheet-like formulas such as `2*(4.5+3.2)*2.8`, named variables (`${wall_h}`), references to other positions (`=Pos("01.02.003")*1.05`) and deductions. In DACH, these rows can be exchanged as GAEB DA XML X31 (quantity determination per REB-VB 23.003, the standard formula catalogue that includes "Formel 91" for free formulas). In the UK, they replace the timesing/squaring columns of dimension paper behind an NRM2 bill.

## Already in the codebase (with file paths)
- `frontend/src/features/boq/grid/cellEditors.tsx`: `FormulaCellEditor` plus `evaluateFormula()`, a CSP-safe recursive-descent parser for numbers and `+ - * / ()` only. The formula is kept in `position.metadata.formula`, and the result overwrites quantity. It has no variables, functions, position references or multiple rows.
- `frontend/src/features/boq/BOQGrid.tsx`: wires the editor in (`formulaCellEditor`, `onFormulaApplied`).
- `backend/app/modules/assemblies/formula_engine.py`: `FormulaEvaluator` (285 LOC), a safe evaluator with `${var}` substitution, `min/max/round/abs/sqrt`, `if()` and `lookup()`. It is only used for assembly component quantities, not for BOQ positions.
- `backend/app/modules/boq/service.py`: the `bim_qty_source` / `pdf_measurement_source` link keys in metadata record where a quantity came from (BIM/PDF), but there is no line-by-line sheet.
- I found no X31 / `QTakeoff` / REB 23.003 support anywhere in `backend/app`.

**Gap:** the BOQ has no measurement-sheet model, API or UI. The backend does not validate or recompute formulas, which today live only in the browser. Formulas cannot refer to other positions and cannot use project variables. There is no X31 import/export.

## Who it helps and how much
- **Small estimators and QS firms:** high value. Today they keep a parallel Excel sheet per position, and moving it into the ERP removes copy-paste errors and makes every quantity auditable for clients.
- **DACH contractors doing billing (*Abrechnung*):** high value. Clients and public authorities often require REB-compliant Aufmaß and X31.
- **Takeoff users:** medium value. PDF, DWG and BIM measurements could each land as one row on the sheet, with the source kept, instead of overwriting the quantity.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium** overall. The core sheet is small to medium; X31 export and the REB formula catalogue are medium on top.
- **Backend (`boq` module):** add a new model `MeasurementLine` (position_id FK, ordinal, description, count, dims JSONB, formula, result, source, source_ref). Add `GET/PUT /api/v1/boq/positions/{id}/measurements`. The service recomputes `position.quantity = Σ result` on the server, reusing or generalising `assemblies/formula_engine.py`. A good place to move it is `backend/app/core/formula.py`, so that BOQ, assemblies and takeoff share one engine. Add a position-reference resolver with cycle detection over a dependency graph. Publish a `boq.position.quantity_changed` event so the cost rollup updates.
- **Validation:** add rules in `boq_quality`: formula parse error, sheet total ≠ position quantity, negative total after deductions, and circular references.
- **Frontend (`features/boq`):** add an expandable sub-grid or drawer under each row (AG Grid detail row) with live preview. Extend `evaluateFormula` with variables and functions, or replace it with a vetted library.
- **Optional module `oe_gaeb_x31`:** maps the sheet rows to `QTakeoff` lines and to the REB formula numbers 00–99.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **simpleeval** (Python, MIT): a sandboxed AST expression evaluator and a drop-in hardening for the backend engine. https://github.com/danthedeckie/simpleeval
- **mathjs** (JS, Apache-2.0; its bundled CSparse part is LGPL): an expression parser with units (`m`, `m2`), useful for unit-aware formulas. https://www.npmjs.com/package/mathjs
- **@formulajs/formulajs** (JS, MIT): Excel function implementations (`SUM`, `ROUNDUP`, `IF`…) for spreadsheet-familiar syntax. https://www.npmjs.com/package/@formulajs/formulajs
- **HyperFormula** (JS, GPL-3.0-only or a paid proprietary licence with unpublished pricing): a full headless spreadsheet engine with cell references. It is powerful, but GPLv3 vs AGPL compatibility has to be checked, and it is heavy. https://hyperformula.handsontable.com/docs/guide/licensing.html
- **GAEB X31 / REB-VB 23.003:** the standard is published by GAEB/BVBS, and the "Das Freie REB Buch" PDF documents the formulas. https://www.bvbs.de/wp-content/uploads/2018/07/Das-Freie-REB-Buch.pdf
- **MCP servers:** I could not verify any MCP server for measurement sheets or GAEB X31. The existing `erp_chat/tools.py` could expose "add measurement line" as an internal tool, with human confirmation as CLAUDE.md requires.

## Priority: 4/5 — a core daily estimator workflow with a clear gap, and roughly 60% of the engine already exists
Formula parsing exists twice already but is isolated. A server-side measurement sheet gives a small firm auditable quantities, takes Excel out of the loop and, in DACH, opens the way to billing compliance through X31.

## Sources
- https://www.gaeb-online.de/gaeb-x31-datei.html
- https://de.wikipedia.org/wiki/X31
- https://www.bvbs.de/wp-content/uploads/2018/07/Das-Freie-REB-Buch.pdf
- https://gaeb-365.online/erfassen-der-mengenansaetze-nach-reb-23-003
- https://www.mwm.de/funktionen/mehr-infos-zu-reb
- https://api.pageplace.de/preview/DT0400.9781317561507_A28768109/preview-9781317561507_A28768109.pdf
- https://pypi.org/project/simpleeval/
- https://www.npmjs.com/package/mathjs
- https://www.npmjs.com/package/@formulajs/formulajs
- https://hyperformula.handsontable.com/docs/guide/licensing.html
