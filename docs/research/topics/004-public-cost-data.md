# 004. Free/Open Public Cost Data Sources (DOT bid tabs, government price lists, cost indices)

## What it does
Gives estimators free, defensible reference prices and escalation factors without a paid RSMeans/BCIS/BKI subscription. Two kinds of data:
1. **Unit-price references**: state DOT average/weighted low-bid unit prices and bid tabulations (TxDOT, Caltrans, Louisiana DOTD, Ohio DOT, Oklahoma DOT, etc.). Strong for civil/sitework (earthwork, asphalt, concrete paving, curbs, sidewalks, drainage); weak for buildings.
2. **Price/escalation indices**: BLS Producer Price Index (construction inputs), FHWA National Highway Construction Cost Index (NHCCI), Eurostat `sts_copi` construction cost/output price indices, Destatis construction price indices (GENESIS), ONS construction output price indices. Also Davis-Bacon prevailing wages from SAM.gov for US public jobs.

The point is to check bid rates against a public benchmark, and to escalate old rates with published indices instead of LLM guesses.

## Already in the codebase (with file paths)
- CWICR regional database loading: `backend/app/modules/costs/router.py` (`/available-databases/`, `/load-cwicr/{db_id}`, vector search).
- Generic Excel/CSV cost import with column auto-detection: `backend/app/modules/costs/router.py` (`/import/file/`). DOT Excel exports could already be loaded this way by hand.
- US pack has only a disabled RSMeans stub: `backend/app/modules/us_pack/config.py` (`cost_database_integrations`).
- Rate escalation exists but asks the **LLM** to estimate inflation factors: `backend/app/modules/boq/router.py` (`/boqs/escalate-rate/`) and `backend/app/modules/boq/service.py` (`escalate_rate`). There is no real index time-series behind it.
- **Gap:** no DOT bid-tab connectors, no index time-series store, no Davis-Bacon lookup.

## Who it helps and how much
- **Small US civil/sitework and paving contractors bidding public work: High.** DOT averages are the same numbers owners' engineers use for their estimates.
- **Any small estimator escalating old quotes or rates: High.** Escalation based on PPI, NHCCI, Eurostat or Destatis can be audited, while LLM guesses cannot.
- **Building or residential GCs: Medium/Low** for DOT data, which covers few building items, but high for indices.
- **US prevailing-wage bidders: Medium.** Davis-Bacon rates matter, but SAM.gov offers only text/PDF downloads and I could not find an API.

## Implementation effort (Medium; `costs`, `boq`, `us_pack`/`dach_pack`/`uk_pack`)
- **New module `public_cost_data`** (manifest depends on `oe_costs`). It holds a `PriceIndexSeries`/`PriceIndexPoint` table and a pluggable `SourceAdapter` interface: `fetch()`, then `normalize()`, then the existing cost-item validation, then `store()`.
- **Index adapters (S each):** BLS API v2 (free key), FHWA NHCCI through the Socrata endpoint at data.transportation.gov, Eurostat SDMX/JSON, and Destatis GENESIS REST. These are periodic jobs that use the existing background or in-process tasks.
- **DOT unit-price adapters (M; one per state, brittle):** most states publish HTML/PDF/Excel rather than APIs. Start with TxDOT and Caltrans, then let regional packs register more states. Imported rows go in as a cost database tagged `source=dot_bid_avg`, with region, letting period, and the sample-size caveat.
- **BOQ hook:** in `escalate_rate`, compute the factor from the stored series first and fall back to the LLM only when no series exists, showing the confidence and the source. Add a `boq_quality` validation rule that warns when a rate falls outside a set band around the DOT average.
- **erp_chat tool:** add `get_price_index(series, from, to)`.

## Building blocks (free/open-source libs, APIs, MCP servers)
- BLS Public Data API v2: free but needs a registration key, renewed yearly. You must know the series IDs because BLS has no catalog. https://www.bls.gov/developers/api_faqs.htm
- FHWA NHCCI: public domain (US government work). The dashboard has an Export button, and a Socrata API is listed on data.gov. https://www.fhwa.dot.gov/policy/otps/nhcci , https://catalog.data.gov/dataset/nhcci
- TxDOT Average Low Bid Unit Prices: free. Current machine-readable format not verified; older versions were text/Excel. https://www.txdot.gov/content/txdot/en/business/letting-bids/average-low-bid-unit-prices.html
- Caltrans Contract Cost Database: free search with weighted averages. No bulk download found; last import shown was 2024-08. https://sv08data.dot.ca.gov/contractcost/
- Louisiana DOTD weighted averages: https://wwwapps.dotd.la.gov/Engineering/lettings/WeightedAverages.aspx ; Ohio DOT Item Master and bid history: https://www.dot.state.oh.us/Divisions/ConstructionMgt/Estimating/Pages/Item-Master.aspx
- Eurostat `sts_copi_q`/`_m`/`_a` (CSTI cost index, CSTO output price index): free. https://ec.europa.eu/eurostat/statistics-explained/index.php/Construction_producer_price_and_construction_cost_indices_overview
- Destatis GENESIS-Online REST/JSON: free, licensed under Data Licence Germany 2.0. https://destatis.de/EN/Service/OpenData/api-webservice.html
- ONS Construction OPIs (quarterly): https://www.ons.gov.uk/businessindustryandtrade/constructionindustry/methodologies/constructionoutputpriceindicesopisqmi
- SAM.gov Davis-Bacon wage determinations: free .txt/PDF. **No official API verified.** https://sam.gov/wage-determinations
- MCP: `stefanoamorelli/fred-mcp-server`, a FRED MCP server whose license is listed inconsistently as AGPL-3.0 or Apache-2.0. FRED mirrors many BLS PPI series. https://mcpservers.org/servers/stefanoamorelli/fred-mcp-server . **No dedicated BLS, DOT or Davis-Bacon MCP server found.**
- IEEE DataPort dataset of DOT bid tabulations (sidewalk items only; license not checked): https://ieee-dataport.org/keywords/dot-bid-tabulations

## Priority: 4/5. Free and defensible data that fixes the LLM-only escalation; DOT scrapers are brittle, so ship the indices first.

## Sources
- https://www.bls.gov/developers/api_faqs.htm
- https://www.fhwa.dot.gov/policy/otps/nhcci
- https://catalog.data.gov/dataset/nhcci
- https://www.txdot.gov/content/txdot/en/business/letting-bids/average-low-bid-unit-prices.html
- https://www.txdot.gov/manuals/des/pse/chapter-5--engineer-s-estimate/section-4--prices.html
- https://sv08data.dot.ca.gov/contractcost/
- https://wwwapps.dotd.la.gov/Engineering/lettings/WeightedAverages.aspx
- https://www.dot.state.oh.us/Divisions/ConstructionMgt/Estimating/Pages/Item-Master.aspx
- https://ec.europa.eu/eurostat/statistics-explained/index.php/Construction_producer_price_and_construction_cost_indices_overview
- https://destatis.de/EN/Service/OpenData/api-webservice.html
- https://www.ons.gov.uk/businessindustryandtrade/constructionindustry/methodologies/constructionoutputpriceindicesopisqmi
- https://sam.gov/wage-determinations
- https://www.dol.gov/agencies/whd/government-contracts/prevailing-wage-resource-book/db-wage-determinations
- https://mcpservers.org/servers/stefanoamorelli/fred-mcp-server
- https://ieee-dataport.org/keywords/dot-bid-tabulations
