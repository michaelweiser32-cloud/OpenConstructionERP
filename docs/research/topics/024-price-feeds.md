# 024. Supplier price feeds and material price indices

## What it does
Pulls official material and construction price indices (US BLS PPI, German Destatis Baupreisindex, UK ONS/DBT construction material price indices, Eurostat construction producer prices) and selected commodity benchmarks (steel, lumber, copper, cement-related energy) into the ERP on a schedule. The estimator can then:
- escalate old unit rates and assemblies from a base date to today using a real index, not a guess;
- see which cost items changed most since the last tender (for example, a lumber spike);
- add index-linked price adjustment clauses to contracts and change orders;
- import supplier price lists (CSV/Excel) with a validation pass (unit, currency, how old the prices are, outliers against the index trend).

## Already in the codebase (with file paths)
- `frontend/src/features/costs/EscalationCalculator.tsx`: an escalation calculator with **hardcoded** yearly percentages per region (labelled as coming from BKI/BCIS/ENR/Eurostat). Nothing is fetched live, and nobody updates the values.
- `backend/app/modules/boq/service.py` (`escalate_rate`, about line 3782) and `boq/ai_prompts.py`: escalation **estimated by the LLM**, with no index data behind it.
- `backend/app/modules/catalog/router.py` (`adjust_prices`): bulk-multiplies catalog resource prices by a manual factor, filtered by type, category or region.
- `backend/app/modules/assemblies/models.py`: `regional_factors` JSON on assemblies (a fixed coefficient per location).
- `backend/app/modules/boq/service.py` (about line 409): an "Escalation Allowance" markup template.
- **Gap:** there is no index time-series model, no fetchers or scheduler for BLS/Destatis/ONS/Eurostat, no supplier price-list import with dates and history, and no link between cost items and an index series.

## Who it helps and how much
Small estimating firms re-use old rates all the time. Indices that are real, cited and refresh themselves make bids and escalation claims defensible. The firm can also show the escalation basis to a client or quantity surveyor. Value is high in volatile years like 2021-2022 and medium otherwise. Supplier price lists help small contractors who buy from 2-5 regular merchants.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** This would be a new module `price_indices` (manifest depends on `costs` and `catalog`):
- `models.py`: `IndexSeries` (source, external_id, region, base period, unit) and `IndexObservation` (period, value). Cost items and assemblies get an optional `index_series_id`.
- `providers/`: one small fetcher per source (BLS, FRED, Destatis GENESIS, ONS, Eurostat/DBnomics). Each implements a common `fetch(series_id, start, end)` interface and runs through the existing background task or workflow engine on a monthly schedule.
- `service.py`: `escalate(amount, series, from_period, to_period)` returns the factor with a citation. The BOQ `escalate_rate` and `EscalationCalculator` would call this first and fall back to the LLM only when no series is mapped.
- `validators.py`: rules for stale prices, unit or currency mismatch, and an outlier check that flags a supplier price more than X% off the index trend.
- Regional packs (`us_pack`, `uk_pack`, `dach_pack`) ship default series mappings. An `erp_chat` tool, "what did steel do since my last bid?", could come later.
- Supplier price lists: CSV/Excel import into `catalog` with `valid_from` and `supplier`, keeping price history.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **BLS Public Data API v2**: free with a registration key: 500 queries a day, 50 series per query, 20 years per query, and the key must be renewed every year. PPI series cover lumber, steel mill products and inputs to construction. https://www.bls.gov/developers/ and https://www.bls.gov/developers/api_faqs.htm
- **FRED API** (St. Louis Fed): free key, mirrors many BLS PPI series, about 120 requests per minute. Check the terms for commercial use. https://fred.stlouisfed.org/docs/api/fred/
- **FRED MCP servers** (community, not official): for example `stefanoamorelli/fred-mcp-server`, whose license is reported as AGPL-3.0 or Apache-2.0 (check the repo). https://github.com/stefanoamorelli/fred-mcp-server
- **Destatis GENESIS-Online REST/JSON**: free, Data Licence Germany 2.0 (attribution). A token comes from a free account. Construction price indices are in table family 61261 (verify the exact table code). https://www.destatis.de/EN/Service/OpenData/api-webservice.html
- **ONS / DBT (UK)**: ONS construction output price indices are published as datasets. The monthly construction material price indices are published by DBT as gov.uk spreadsheet downloads. I found no official API for them, so they would be scraped from the files. https://www.gov.uk/government/statistics/building-materials-and-components-statistics-december-2025
- **Eurostat dissemination API / DBnomics**: no auth needed. The DBnomics Python client is `dbnomics` (AGPL-3.0, the same license as this project). https://docs.db.nomics.world/web-api/
- **World Bank Pink Sheet**: free monthly commodity prices (metals, energy, timber logs), as an Excel download. https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet
- **Exchange data (LME steel or copper, CME lumber futures)**: I did not verify the terms. Assume a paid licence is needed for redistribution, so leave these out of core.
- **Supplier price feeds**: I found no open standard or MCP server. Use CSV/Excel import, and for DACH, use the existing GAEB/DATANORM-style file import as a later step.

## Priority: 4/5 — the escalation features already exist but run on hardcoded numbers and LLM guesses; free official APIs make them trustworthy at Medium effort.

## Sources
- https://www.bls.gov/developers/api_faqs.htm
- https://fred.stlouisfed.org/docs/api/fred/
- https://github.com/stefanoamorelli/fred-mcp-server
- https://www.destatis.de/EN/Service/OpenData/api-webservice.html
- https://www.ons.gov.uk/businessindustryandtrade/constructionindustry/methodologies/constructionoutputpriceindicesopisqmi
- https://www.gov.uk/government/publications/building-materials-and-components-methodology/building-materials-and-components-statistics-material-price-indices-methodology
- https://docs.db.nomics.world/web-api/
- https://pypi.org/project/dbnomics/
- https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/world-bank-commodities-price-data-the-pink-sheet
