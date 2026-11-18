# 007. Labor / Crew / Equipment Rate Builder (productivity + burden)

## What it does
A rate builder works out unit rates from first principles, the way estimators actually build them:
- **Labor burden**: base wage + fringe (benefits, union/pension) + payroll taxes + insurance (workers' comp, liability) gives the **burdened hourly rate**. The German equivalent is the EFB-Preisblatt 221/222 chain: Mittellohn → lohngebundene Kosten → Lohnnebenkosten → Kalkulationslohn → Verrechnungslohn.
- **Equipment hourly**: ownership costs (depreciation, cost of money) + operating costs (fuel, FOG, repairs, tires), or a rental rate plus operating cost. This follows the USACE EP 1110-1-8 method.
- **Crew**: a named mix of trades and equipment (e.g. "C-14: 1 foreman, 4 carpenters, 1 laborer, 1 crane"). It gives a blended cost per crew-hour.
- **Productivity**: daily output or units per hour per crew gives labor-hours per unit and cost per unit. Condition factors adjust it for weather, height, congestion and overtime.
- Changing one wage or the burden % re-prices every assembly and BOQ position that uses it. This "what-if" is the main value.

## Already in the codebase (with file paths)
- `backend/app/modules/catalog/models.py`: `CatalogResource` has `resource_type` (material / equipment / labor / operator), a flat `base_price` and a free `specifications` JSON. It has **no wage/fringe/burden fields and no equipment ownership/operating split**.
- `backend/app/modules/assemblies/models.py`: `Component` has `factor`, `quantity`, `unit_cost` and a link to a catalog resource. `assemblies/router.py` (around line 248) and `service.py` (around line 542) only *guess* labor/equipment type from keywords.
- `backend/app/modules/costs/router.py` (around lines 1627–1969): the CWICR import pulls `labor_hours` into item metadata. This is a usable seed for productivity norms.
- `backend/app/modules/schedule/schemas.py`: `LaborCostByPhase` reporting only.
- **Gap**: there is no crew entity, no productivity rate (units/hr) entity, no burden calculator, no equipment rate calculator, and no cascade re-pricing. Regional packs (`us_pack`, `dach_pack`) carry no wage or burden templates.

## Who it helps and how much
**High value** for small GCs and subcontractors who self-perform work (concrete, framing, sitework, MEP subs). They bid on their own crews, not on book prices. Burden is commonly under-counted (vendors claim labor is underestimated by 20–35%; treat that as a vendor claim). Prevailing-wage (Davis-Bacon) bidders need wage plus fringe per classification. DACH bidders on public work must fill in EFB 221/222 forms. A builder that outputs those numbers directly is a strong differentiator against spreadsheets.

## Implementation effort
**Medium**. Best done as a new module `rates` (`oe_rates`, depends on `oe_catalog` and `oe_assemblies`):
- `models.py`: `LaborClass` (base wage, fringe, burden profile), `BurdenProfile` (% or per-hour items: taxes, WC, insurance; regional), `EquipmentRate` (ownership/hr, operating/hr, or rental + operating), `Crew` and `CrewMember` (labor class or equipment, qty), `ProductivityRate` (crew, unit, output/hr, condition factors).
- `service.py`: pure `Decimal` calculators: burdened rate, crew $/hr, labor-hours/unit, $/unit.
- Hooks/events: publish a `rates.changed` event. Assemblies subscribe to it and recompute components that link to a crew or productivity rate, then BOQ recomputes. This is shown as a reviewable diff, not applied silently.
- Validators: zero wage, burden < 10% or > 80%, productivity outliers vs CWICR `labor_hours`, and crews without a foreman.
- Regional packs ship default burden profiles (US FICA/FUTA, DE Sozialkassen) as JSON seed data. The frontend adds a crew editor and links "use crew" into the assembly editor.

## Building blocks
- **USACE EP 1110-1-8**: a free public-domain equipment rate method and tables. They are regional and the latest found edition is older, so verify it. https://www.usace.army.mil/Cost-Engineering/EP1110-1-8
- **SAM.gov wage determinations**: free Davis-Bacon wage + fringe by county and craft. I could **not verify a public API** for them, so treat them as manual or file import. https://sam.gov/wage-determinations
- **BLS OEWS**: free hourly wages by construction NAICS. The BLS Public Data API exists, but I could not fetch it here (host blocked), so verify the limits. https://www.bls.gov/oes/current/naics2_23.htm
- **RSMeans (Gordian)**: crew tables and labor rates. Commercial. Gordian says it offers API or flat-file delivery, but no public API docs were found. https://www.rsmeans.com/
- **BidSheet**: a GPLv3 open-source sub estimating app with crew costs. Use it as a reference only (could not fetch it to verify the repo). https://bidsheet.pages.dev/
- **EFB 221/222 structure** (DACH): https://www.bauprofessor.de/lohnkosten-efb-preisblaetter/
- **MCP**: no MCP server for crew, productivity or wage rates was found. Expose the calculator through `erp_chat/tools.py` instead.
- Python stdlib `decimal` covers all the maths. No new dependency is needed.

## Priority: 4/5. Core estimating mechanics that small self-performing contractors rely on daily; medium effort on top of the existing catalog and assemblies, with no external dependency.

## Sources
- https://www.usace.army.mil/Cost-Engineering/EP1110-1-8
- https://webarchive.library.unt.edu/web/20161019151924/http://www.nww.usace.army.mil/Missions/CostEngineering/Historical.aspx
- https://sam.gov/wage-determinations
- https://www.dol.gov/agencies/whd/government-contracts/prevailing-wage-resource-book/db-wage-determinations
- https://www.bls.gov/oes/current/naics2_23.htm
- https://www.rsmeans.com/what-is-construction-estimating
- https://jocexcellence.org/wp-content/uploads/2023/10/joc-RSMeans-how-toUPB-suffolk-county.pdf
- https://www.gordian.com/uploads/2021/10/RSMeans_data_One_Sheet_10142021_high.pdf
- https://bidsheet.pages.dev/
- https://www.bauprofessor.de/lohnkosten-efb-preisblaetter/
- https://www.bauprofessor.de/mittellohn/
- https://esub.com/blog/how-to-calculate-labor-cost-in-construction
