# 003. Regional cost bases and location factors (CWICR, RSMeans, BKI, BCIS, city cost indices)

## What it does
Turns a national or base-city unit rate into a local, current-dated rate. It does this in two steps:
- **Location factor:** a multiplier per city, postcode or county. RSMeans City Cost Index, BKI Regionalfaktoren and BCIS location factors all work this way.
- **Time/escalation index:** a correction from the price base date to the bid date, using a tender or producer price index.

A small estimator can then reuse one cost library across jobs in different towns, and keep old estimates and assemblies current without re-pricing every line.

## Already in the codebase (with file paths)
- `backend/app/modules/costs/models.py`: `CostItem.region` (String 50), unique on `(code, region)`. It stores regional price sets of CWICR side by side, but has no factor or index table.
- `backend/app/modules/assemblies/models.py`: `regional_factors` JSONB on assemblies. `backend/app/modules/assemblies/service.py` (around lines 517-525) applies `regional_factors[region]` when an assembly is pushed into the BOQ. This is the only working location factor logic.
- `frontend/src/features/projects/CreateProjectPage.tsx` (around lines 250, 346, 594): the UI has a "Regional price coefficient" field and sends `regional_factor`. **No backend code reads it.** A grep for `regional_factor` outside assemblies returns nothing, so the value is silently dropped. This is a quick bug to fix.
- `backend/app/core/marketplace.py`: CWICR UK/DACH catalogue entries that mention "BCIS regional indices" and "BKI benchmark". Around line 821 there is an `analytics-benchmarks` "Cost Benchmarks (BKI/BCIS/RSMeans)" entry with no implementation behind it.
- `backend/app/modules/us_pack/config.py` and `uk_pack/config.py`: describe the data sources as text only.

**Gap:** no `LocationIndex` or `PriceIndex` tables, no escalation, no per-project factor, and no importers for published indices.

## Who it helps and how much
- **High value:** contractors and estimators who bid across several cities or regions, or who reuse estimates more than a few months old.
- Applying one project-level factor plus an escalation index is a standard step in an estimate (CCI is how RSMeans users localise national averages).
- Without it, users hand-edit rates or keep spreadsheets.
- Cost is low for users: most of the value comes from user-entered factors plus free public indices. Licensed data (RSMeans, BKI, BCIS) is a bring-your-own-subscription add-on.

## Implementation effort
**Medium.** Modules touched: `costs`, `projects`, `boq`, `assemblies`, and the regional packs.

1. Add `costs/models.py` → `LocationFactor(source, region_code, postcode/admin_area, factor, valid_from)` and `PriceIndex(source, series_id, period, value, base)`, with an Alembic migration.
2. Persist `regional_factor`, `location_code` and `price_base_date` on Project. This fixes the dropped field.
3. Add a BOQ service hook (`hooks.py`, filter `boq.position.rate`). It computes `rate × location_factor × (index_bid / index_base)`, stores both factors in position `metadata` for audit, and always shows them as a suggestion for the user to confirm.
4. Each regional pack seeds a default factor set and index series: US→FRED/BLS PPI, DE→Destatis 61261, EU→Eurostat.
5. Add a CSV importer for licensed factor tables (RSMeans CCI, BKI, BCIS). These are user-supplied; we do not redistribute them.
6. Add a validation rule `boq_quality.stale_price_base` that warns when the price base is more than 12 months old, and one that warns when the factor is outside 0.6–1.6.
7. Optionally add an `erp_chat/tools.py` tool: "re-price this BOQ for city X".

## Building blocks
- **CWICR** (DDC, already integrated): multi-region price sets. Repo: https://github.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR. Check the repo for the licence; third-party listings disagree.
- **FRED API** (free key; BLS PPI inputs to construction, e.g. WPUIP2312001): https://fred.stlouisfed.org/series/WPUIP2312001. Public-domain BLS data.
- **Eurostat SDMX API** (free, no key; construction cost/producer price datasets): https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-faq. The exact dataset code (`sts_copi_*`) was not verified.
- **Destatis GENESIS-Online** (free; Baupreisindex tables 61261-0001…0016): https://www.destatis.de/EN/Themes/Economy/Prices/Construction-Prices-And-Real-Property-Prices/database-teaser.html. The API needs registration; parameters not verified.
- **RSMeans City Cost Index** (Gordian, paid; reported prices conflict, about $356/yr to $2.2k–6.7k/seat/yr): https://www.rsmeans.com/rsmeans-city-cost-index. **No public API documentation found.**
- **BCIS location factors and TPI** (RICS, subscription CapX/TotX, postcode lookup): https://bcis.co.uk/insight/are-you-using-the-right-bcis-index/. **No public API found.**
- **BKI Regionalfaktoren** (paid books and Kostenplaner, all German Stadt- and Landkreise plus AT/EU): https://www.baulinks.de/webplugin/2026/1646.php4. **No API found.**
- **MCP servers:** none verified for RSMeans, BCIS or BKI. No official FRED, Eurostat or Destatis MCP server was verified either. Use plain HTTP clients (`httpx`, already a dependency).

## Priority: 4/5 — the fix is cheap (the UI field already exists but is dropped), it touches almost every estimate a small business makes, and free public indices give it full value without licensing.

## Sources
- https://www.rsmeans.com/rsmeans-city-cost-index
- https://help.sagecm.intacct.com/Content/Modules/Estimating/Estimates/AddEstimate/EstimatePropertiesRSMeansCityCostIndexFactor.htm
- https://www.getapp.com.au/software/117995/rsmeans
- https://oneestimate.ai/en/compare/oneestimate-vs-rsmeans
- https://bcis.co.uk/insight/are-you-using-the-right-bcis-index/
- https://bcis.co.uk/bcis-capx-indices/
- https://www.baulinks.de/webplugin/2026/1646.php4
- https://fred.stlouisfed.org/series/WPUIP2312001
- https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-faq
- https://www.destatis.de/EN/Themes/Economy/Prices/Construction-Prices-And-Real-Property-Prices/database-teaser.html
- https://www.destatis.de/DE/Presse/Pressemitteilungen/2026/10/PD26_360_61261.html
- https://relatedrepos.com/gh/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR
