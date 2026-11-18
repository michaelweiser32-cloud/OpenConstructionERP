# 001. Assembly / Recipe Library Depth: Nested & Parametric Assemblies, Crew + Material + Equipment Recipes

## What it does
An assembly (recipe, "Kalkulationsansatz") bundles the resources needed for one unit of work, e.g. 1 m2 of 24 cm C30/37 wall = concrete + rebar + formwork + crew hours + pump time. "Depth" adds three things:
- **Parametric assemblies**: the user enters variables (height, thickness, spacing, finish grade) and component quantities are computed by formula. Sage Estimating works this way: a factor or formula on each item, driven by variable values entered at takeoff.
- **Nested assemblies**: an assembly can contain other assemblies ("Wall" = "Formwork set" + "Rebar set" + "Concrete pour"), so you edit a sub-recipe once and every parent rolls up the change.
- **Crew recipes**: a named crew (e.g. 1 foreman + 2 carpenters + 1 laborer + mixer) with hourly costs and a daily output. Labor hours per unit are derived as crew-hours/day divided by daily output, the RSMeans crew model.

## Already in the codebase (with file paths)
- `backend/app/modules/assemblies/models.py`: flat `Assembly` -> `Component` (cost_item_id / catalog_resource_id, factor, quantity, unit_cost), `regional_factors`, `bid_factor`. There is no parent/child assembly link and no crew entity.
- `backend/app/modules/assemblies/formula_engine.py`: a 285-line safe evaluator with `${param}` substitution, conditionals and lookup tables. **It is not imported anywhere** in `backend/app`, so parametric assemblies are written but not wired in. This is the largest quick win.
- `backend/app/modules/assemblies/router.py`: CRUD, clone, apply-to-BOQ, import/export, reorder, and a keyword heuristic (`_infer_component_type`, ~L248) that tags components as labor, equipment or material.
- `backend/app/modules/assemblies/service.py` (`apply_to_boq`, ~L496): splits resources by type when applying to the BOQ.
- `backend/app/modules/costs/router.py` (~L1627-1960): the CWICR import already carries `total_labor_hours_all_personnel` and labor cost, which is raw material for crew productivity.
- Frontend: `frontend/src/features/assemblies/` (list, editor and create pages). No parameter or crew UI.

## Who it helps and how much
For small GC and specialty estimators this is high value. Most of their work is repeating the same 30-100 recipes (slab, stud wall, drywall, roofing), and parametric recipes turn an hour of spreadsheet copying into entering a few variables. Nesting stops duplication drift when rates change. Crew recipes let a company use its *own* productivity and wage rates, which is the main thing generic cost databases get wrong. It is also a differentiator against cheap SaaS estimators, which usually offer only flat item lists.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium**, mostly inside `assemblies`, with small changes to `boq`, `costs` and `validation`.
1. **Parametric (S)**: add `parameters: JSONB` (name, type, default, unit, min/max) to `Assembly` and `quantity_formula: str|None` to `Component`. Evaluate with `FormulaEvaluator` in the service at apply-to-BOQ and preview time, and store the resolved values in position `metadata`. Expose `POST /assemblies/{id}/evaluate/`.
2. **Nested (M)**: add `child_assembly_id` (nullable FK to `oe_assemblies_assembly`) on `Component` (an XOR with cost_item). Do a recursive roll-up with cycle detection and a depth cap of about 5, and pass parent parameters down to children. Emit an `assemblies.assembly.updated` event so parents and BOQ positions can be flagged stale.
3. **Crews (M)**: new models `Crew` and `CrewMember` (resource, count, hourly rate) plus `daily_output`. A crew can be a component type. Compute hours/unit = crew-hours / daily output, and offer a crew seed from CWICR labor hours.
4. **Validation**: add rules (circular nesting, formula errors, a zero-output crew, unit mismatch between parent and child) as a `ValidationRule` set registered via the core engine.
5. **Frontend**: a parameter form plus a tree editor in `AssemblyEditorPage.tsx`.
These are Alembic migrations scoped to the module, and the manifest does not change.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Existing `formula_engine.py`**: the in-house evaluator. Reuse it and add no new dependency.
- **simpleeval** (https://github.com/danthedeckie/simpleeval): MIT-licensed. An alternative AST-based sandbox, though its own docs warn it does not protect against resource exhaustion.
- **RSMeans Data Online** (https://www.rsmeans.com/2026-assemblies-costs-book): commercial and paid. Offers 19,500+ assemblies and a crew model. An API is listed as a feature, but I could **not** verify any public API documentation, so this is enterprise-module territory only.
- **Sage Estimating assembly/variable docs** (https://help-sageestimating.na.sage.com/en-us/21_1/Content/assembly/how_takeoff_quantities_are_calculated_for_assemblies.htm): a UX reference only (proprietary).
- **MCP**: community servers exist, e.g. blackmount-construction-mcp (MIT, https://pypi.org/project/blackmount-construction-mcp) and construct-cost-mcp (https://playbooks.com/mcp/abhigit-trimble/construct-cost-mcp). Neither handles nested or parametric assembly authoring, and I did not verify their quality or maintenance. A better route is to expose `evaluate_assembly` and `search_assemblies` as tools in `backend/app/modules/erp_chat/tools.py`.

## Priority: 5/5 — the formula engine already exists unwired, and recipes are the core of every small-shop estimate; high value for moderate, well-contained effort.

## Sources
- https://help-sageestimating.na.sage.com/en-us/21_1/Content/assembly/how_takeoff_quantities_are_calculated_for_assemblies.htm
- https://help-sageestimating.na.sage.com/en-us/25_2/Content/ModelEstimating/UsedInModelsTOC/AboutModels/understanding_model_estimating.htm
- https://www.rsmeans.com/2026-assemblies-costs-book
- https://fims.doe.gov/caisinfo/Meetings/2024/Presentations/2_Gordian.pdf
- https://www.softwareadvice.com/construction/rsmeans-online-profile/
- https://github.com/danthedeckie/simpleeval
- https://pypi.org/project/blackmount-construction-mcp
- https://playbooks.com/mcp/abhigit-trimble/construct-cost-mcp
