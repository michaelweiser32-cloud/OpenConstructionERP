# 100. Onboarding, sample data and first-run experience for small contractors

## What it does
The path from a fresh install to a first real estimate. A small contractor (1 to 20 people) decides in the first session whether to keep a tool. A good first run has: a short setup wizard (company type, region, currency, module set); sample projects at their scale (bathroom remodel, roof, small extension, not a hospital); a "bring your data" step for customers and price lists from Excel/CSV; a getting-started checklist (first estimate, PDF quote, invoice); and safe removal of sample data that never leaks into real reports.

## Already in the codebase (with file paths)
Much of this already exists. Most of the gap is in content and in how the pieces connect, not in infrastructure.
- **Setup wizard:** `frontend/src/features/onboarding/OnboardingWizard.tsx` (about 1,900 lines). It is a multi-step wizard: start choice, profile, module review, finish.
- **Company presets:** `backend/app/core/onboarding_presets.py` defines five presets: general_contractor, estimator, project_management, architecture_engineering and full_enterprise. None of them is aimed at a remodeler, a trade or specialty subcontractor, or a one-person shop.
- **Demo projects:** `backend/app/core/demo_projects.py` (about 7,800 lines) holds five demo templates: residential-berlin, office-london, medical-us, warehouse-dubai and school-paris. All five are mid-size or large commercial jobs. Each is tagged `is_demo` in the project metadata, and `_seed_module_data` fills the other modules.
- **Demo endpoints in `backend/app/main.py`:** `GET /api/demo/status`, `DELETE /api/demo/uninstall/{demo_id}`, `DELETE /api/demo/clear-all`, and a seeded demo account (`_seed_demo_account`).
- **Spotlight tour:** `frontend/src/shared/ui/OnboardingTour.tsx` is a custom tour driven by `data-tour` selectors. It has five generic steps.
- **Excel/CSV import:** `backend/app/modules/contacts/router.py` and `backend/app/modules/costs/router.py` both have `POST /import/file/` and a template download. The `xlsx` package is already a frontend dependency.
- **Seed scripts:** `backend/app/scripts/seed_*.py` and `frontend/src/features/setup/DatabaseSetupPage.tsx`.

**Gaps:**
1. There are no small-job demo templates.
2. There is no small-contractor or trade preset.
3. The wizard has no step that links to the contact and cost-item imports.
4. There is no persistent getting-started checklist that tracks real activity.
5. Nothing clearly marks the sample data as sample data across reports, dashboards and exports, for example by excluding `is_demo` projects from KPIs by default.

## Who it helps and how much
- **High value for small remodelers, trade subcontractors and solo estimators.** They have no implementation consultant, so self-serve onboarding decides whether they adopt the tool.
- **Commercial tools rely on people.** Buildertrend and JobTread use dedicated onboarding staff (JobTread offers no free trial for this reason); Joist sells instant signup with a 14-day trial. An open-source ERP has no onboarding staff, so the product must do that work.
- **Low extra value for enterprises,** who will run their own rollout.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Overall: Medium.** Most of the work is content and wiring, not new infrastructure.
1. **Add 3–4 `DemoTemplate`s** to `core/demo_projects.py`, for example bathroom remodel, roof replacement, small house extension and a trade fit-out. Each should be small (20–60 positions) and localised through the existing i18n and regional packs. *Small–Medium.*
2. **Add `remodeler`, `trade_contractor` and `solo_estimator` presets** to `onboarding_presets.py`, mirrored in the wizard's preset list. They enable a lean module set: boq, costs, assemblies, contacts, reporting and finance. *Small.*
3. **Add an "Import your data" wizard step.** It reuses the existing contacts and costs `/import/file/` endpoints and their template downloads. Papa Parse could optionally give a client-side preview. Validation runs as part of the import, as the project rules require. *Small.*
4. **Build a getting-started checklist.** One option is a small `onboarding` module with a manifest. It would subscribe to event-bus events such as project created, BOQ position added, report exported and invoice created, store progress per user, and expose `GET /api/v1/onboarding/progress` for a dashboard widget. *Medium.*
5. **Keep sample data out of real figures.** Add a "Sample" badge, and exclude `is_demo` projects in reporting, dashboard and finance aggregations unless the user opts in. *Small.*
6. **Write tours per page** (BOQ editor, cost browser) using the existing `OnboardingTour` steps. No new dependency is needed. driver.js (MIT) is a fallback if the custom tour gets hard to maintain. *Small.*

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **driver.js:** a vanilla JS product-tour library, MIT. https://driverjs.com/
- **Shepherd.js / react-shepherd:** dual AGPL-3.0 plus commercial licence. It is compatible with this project's AGPL licence, but it limits commercial-edition use, so driver.js or the in-house tour is the safer choice. https://github.com/shipshapecode/shepherd
- **Papa Parse:** an in-browser CSV parser, MIT, with no dependencies. https://github.com/mholt/PapaParse
- **Faker (JS):** an MIT generator for synthetic names and addresses, so sample customers and suppliers contain no real data. https://github.com/faker-js/faker
- **MCP:** I could not verify any onboarding-specific MCP server, and none is needed. The existing `erp_chat` tools could, however, answer "how do I…" questions during the first session.

## Priority: 4/5 — the infrastructure (wizard, demos, install/remove, imports) already exists and is cheap to retarget at small jobs, and self-serve onboarding is what decides whether a small contractor without onboarding staff adopts the tool.

## Sources
- https://jobtread.com/invite
- https://buildertrend.com/blog/how-to-use-buildertrend/
- https://www.joist.com/estimating-invoicing-software/
- https://driverjs.com/
- https://github.com/shipshapecode/shepherd
- https://inlinemanual.com/blog/driverjs-vs-introjs-vs-shepherdjs-vs-reactour
- https://github.com/mholt/PapaParse
- https://github.com/faker-js/faker
