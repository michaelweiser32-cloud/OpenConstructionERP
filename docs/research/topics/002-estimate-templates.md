# 002. Estimate templates by project type and copy-from-past-project

## What it does
A small contractor rarely starts an estimate on a blank sheet. They open "the last kitchen remodel" or "the last flat-roof re-cover", copy it, then change the quantities, rates and scope. This feature has two parts:

1. **Starter templates by project type.** These are pre-structured BOQs with sections, typical positions, units and parametric quantities, for the jobs small firms actually bid: residential new-build or extension, interior fit-out (office or retail), roofing (pitched re-roof, flat-roof membrane), small commercial shell and core, and remodels (kitchen, bath).
2. **A user template library and copy-from-past-project.** Users can save any BOQ (or one section of it) as a company template. They can also clone a BOQ from any earlier project into a new project, choosing whether to keep quantities, keep or refresh rates (re-price from the current cost database or apply an escalation %), and keep or drop markups.

Competitors treat this as core. Clear Estimates, Projul, OneClickContractor and ConstructionOnline all offer "duplicate estimate into a new project". JobTread and Buildxact keep budget templates in a catalog (kitchen, bath, deck). Buildertrend imports saved estimate templates.

## Already in the codebase (with file paths)
- `backend/app/modules/boq/templates.py` (~1,270 lines): 8 hard-coded built-in templates: residential (multi-family, 3-5 floors), office, warehouse, school, hospital, hotel, retail mall, bridge. Positions have rates and are scaled by `area_m2`.
- `backend/app/modules/boq/router.py`: `GET /boqs/templates/`, `POST /boqs/from-template/` (`BOQFromTemplateRequest`: project_id, template_id, area_m2, boq_name in `schemas.py`), `POST /boqs/{id}/duplicate/` and `POST /positions/{id}/duplicate/`.
- `backend/app/modules/boq/service.py` `duplicate_boq()`: deep-copies positions and markups, but **only into the same project**, as "<name> (Copy)".
- `backend/app/modules/projects/router.py`: the project list filter accepts `status=template`. A notion of template projects exists, but there is no clone-project endpoint.
- `frontend/src/features/boq/TemplatesPage.tsx`: UI for picking a built-in template.
- `backend/app/modules/assemblies/`: reusable assemblies, which are the building blocks a template can reference.

**Gap:**
- No small-business templates: the built-in set is all large buildings. Fit-out, roofing, remodel and small commercial are missing.
- Templates are Python code, not user data, so users can't "save as template" or edit them and there is no per-tenant library.
- No cross-project copy.
- No "re-price on copy" or escalation option.
- No scale drivers other than m² (e.g. roof area plus pitch, number of rooms).
- No template marketplace or packaging through the module system.

## Who it helps and how much
Mainly owner-estimators and small GC/remodel/roofing firms that bid the same 3–5 job types again and again. Industry guidance (JLC) recommends a template library as the fastest route to consistent estimates. Copying a past job cuts a first draft from hours to minutes and keeps company know-how (waste factors, forgotten items) in reuse. **Value: High** for small firms. It is less important for large firms with dedicated estimators and cost databases.

## Implementation effort
**Medium. Modules touched: `boq`, `projects`, `assemblies`, `costs`, plus the frontend `features/boq`.**
- Add a `BOQTemplate` model to `boq/models.py`: tenant_id, name, project_type, region, currency, drivers (JSON parameter schema such as `area_m2`, `roof_pitch`, `rooms`), sections and positions as JSONB with quantity formulas, and assembly/cost-item references. Seed the existing 8 plus new small-business ones from JSON files under `data/seeds/templates/`, so a new template is a JSON file, in the same spirit as i18n.
- Endpoints:
  - `POST /boqs/{id}/save-as-template`
  - `POST /boqs/{id}/copy-to-project` with options `{target_project_id, keep_quantities, rate_mode: keep|reprice|escalate, escalation_pct, include_markups}`
  - `POST /projects/{id}/clone`
- Re-pricing resolves `cost_item_id` against the current `costs` database. Run the `boq_quality` validation on every created or copied BOQ so stale or zero rates are flagged, which honours the validation-first rule.
- Publish a `boq.template_applied` event on the event bus. Regional packs (`us_pack`, `uk_pack`, `dach_pack`) can ship their own template JSON through the module loader, and later through the marketplace.
- Add an `erp_chat` tool ("start an estimate like project X") that returns a **proposal** for human confirmation.

## Building blocks
- Existing internal code: `boq/templates.py`, `duplicate_boq()`, the assemblies module, and the event bus and module loader. No new dependency is needed. Formula evaluation can use a safe-expression parser such as `simpleeval` (MIT, https://github.com/danthedeckie/simpleeval) or a small hand-written evaluator.
- Escalation indices, optional:
  - US BLS PPI construction-input series (public-domain data; the AGC republishes the tables monthly). The BLS API at https://www.bls.gov/developers/ is free with registration, but its terms **could not be verified in this session** because the host was blocked.
  - Eurostat construction cost index `sts_copi` (open data), also **not verified here**.
- MCP: **I found no dedicated MCP server for estimate templates.** Not needed; the existing `erp_chat` tools layer is enough.
- Commercial reference designs, for UX only and not integrations: JobTread catalog and budget templates, Buildxact templates, Buildertrend estimate templates (all paid SaaS).

## Priority: 5/5 — It covers the most frequent small-contractor workflow and most of the plumbing already exists; what's missing is the small-job content, user-saved templates and cross-project copy.

## Sources
- https://www.clearestimates.com/duplicate-project-to-save-time
- https://projul.com/features/clone-projects-and-estimates-and-tasks/
- https://help.constructiononline.com/en/duplicate-an-estimate-1
- https://help.oneclickcontractor.com/knowledge/how-to-duplicate-and-estimate-in-one-click-contractor
- https://www.jobtread.com/product-updates/2022-09-26-adding-budget-templates-to-your-catalog
- https://www.jobtread.com/product-updates/2024-06-04-template-library
- https://buildertrend.com/help-article/estimate-overview/
- https://help.buildxact.com/en/articles/3038614-3-ways-to-create-a-template
- https://www.jlconline.com/remodeling/estimating-using-templates_o/
- https://www.agc.org/sites/default/files/users/user21902/PPI%20Tables%202026_10.pdf
- https://github.com/danthedeckie/simpleeval
