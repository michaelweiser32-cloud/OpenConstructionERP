# 006. Markups: overhead, profit, contingency, escalation, bonds, insurance, sales tax/VAT

## What it does
Turns direct cost (sum of BOQ positions) into a bid price. A markup stack typically adds site and general overhead, profit, risk or contingency, escalation to the build date, bonds (bid, performance, payment), insurance (CAR or general liability), and finally sales tax or VAT. Small contractors need three things from it: stack templates they can reuse, the right **base** for each line (for example US sales tax on materials only, or labor burden on labor only), and an audit trail showing how the bid total was reached.

## Already in the codebase (with file paths)
- `backend/app/modules/boq/models.py` has `BOQMarkup` (table `oe_boq_markup`) with these fields: `markup_type` (percentage/fixed/per_unit), `category` (overhead/profit/tax/contingency), `apply_to` (direct_cost/cumulative), `sort_order`, `is_active`, and `metadata`.
- In `backend/app/modules/boq/service.py`:
  - Regional markup templates exist for DE (BGK/AGK/Wagnis/Gewinn/MwSt), UK (NRM prelims/OH&P/risk/VAT) and other regions.
  - A new BOQ gets its region's template applied automatically (`apply_default_markups`).
  - `_calculate_markup_amounts` does the calculation, but `per_unit` **returns 0** (it is not implemented), and `"subtotal"` is treated the same as `direct_cost`.
- `backend/app/modules/boq/router.py` has CRUD endpoints at `/boqs/{id}/markups` plus `apply-defaults`. It also has an AI endpoint, `/boqs/escalate-rate/`, which uses an LLM guess (prompt in `ai_prompts.py`). No index data sits behind it.
- On the frontend, `frontend/src/features/boq/MarkupPanel.tsx`, `BOQSummaryPanel.tsx`, `pdfReport.ts` and `exportExcel.ts` render the markups.
- The regional packs (`dach_pack/config.py`, `latam_pack/config.py`, `asia_pac_pack/config.py`) contain static VAT and tax-rate configs.
- Unrelated: `backend/app/modules/markups/` is for drawing annotations, not pricing.

**Gaps:**
1. Markups can't be based on a cost type. Labor, material, equipment and subcontract can't be split, so materials-only sales tax and labor burden can't be modelled.
2. There is no tiered or sliding-scale type for surety bonds.
3. There is no data-driven escalation from a price index over the project duration.
4. There is no jurisdiction tax lookup for US sales tax, which varies by state, county and city.
5. Markups can't be applied per section or trade, and there is no override at position level.
6. Reusable company stack templates can't be saved alongside the regional ones.
7. There are no validation rules for markups, such as "VAT missing" or "profit below 0".

## Who it helps and how much
It matters to every small estimator: a bid can't be submitted without a correct markup stack, and a wrong base or order directly costs margin. The basic stack already works, so the remaining value is correctness and speed. US subcontractors are hit hardest, because they need materials-only sales tax and bond pricing. DACH users already have a good fit (BGK/AGK/W&G).

## Implementation effort (Small/Medium/Large, module(s) touched, sketch)
**Medium, mostly in `oe_boq`.** A small first step can be done in about a week.
- Extend `apply_to` with `cost_type:labor|material|equipment|subcontract` and `section:<id>`. Positions already carry `metadata`, and the cost-type breakdown can come from assemblies or resources.
- Implement `per_unit`, and add a `tiered` type whose brackets are stored in `metadata`, for example `[{"upto":100000,"rate":2.5},{"upto":500000,"rate":1.5},...]`.
- Add an `escalation` type with `base_date`, `midpoint_date` and `index_series`. The factor comes from an index cache filled by an optional regional-pack or integrations job (BLS for the US, Destatis for DE). Showing the factor for user confirmation follows principle 7.
- Add `company_templates`, a new table or a `projects` setting, and expose it through a hook (`boq.markup_templates` filter) so regional packs and plugins can contribute templates.
- Add validation rules under `core/validation/rules/boq_quality.py`, such as `markup_tax_missing`, `markup_negative_profit` and `markup_contingency_out_of_range`.
- Add an `erp_chat/tools.py` tool, such as "what if profit = 8%?". An external tax connector (Avalara) would be an optional plugin, not core.

## Building blocks (libs, APIs, MCP servers)
- **Python `decimal`** (stdlib). Already used, so no new dependency is needed.
- **ibericode/vat-rates**: EU VAT rates as JSON, MIT licensed and community maintained, with no accuracy guarantee. It could be cached into the regional packs. https://github.com/ibericode/vat-rates
- **BLS Public Data API v2**: US PPI series, including inputs to construction industries. Free with a registration key. https://www.bls.gov/developers/
- **Destatis GENESIS-Online web service**: German price indices, including the Baupreisindex. Free under Datenlizenz Deutschland 2.0. **`pystatis`** is an open-source Python wrapper for it. https://www.destatis.de/EN/Service/OpenData/api-webservice.html · https://correlaid.github.io/pystatis/pystatis.html
- **Avalara AvaTax**: commercial US sales-tax calculation API (paid; pricing not public). Avalara has announced **official MCP servers**, including AvaTax, on its blog. I could not verify their endpoints or availability; Avalara says the details are on developer.avalara.com. Community AvaTax MCP servers also exist, such as JoshMcMillen/avatax-mcp-server, but they are unvetted. This only makes sense as an optional plugin.
- **Surety rate tiers**: typical market tiers are roughly 2.5% on the first $100k, 1.5% on the next $400k and 1.0% on the next $500k. These are examples from vendors, not a standard, so they belong in an editable template, never hard-coded.
- **BLS price adjustment guide**: guidance on escalation clauses using PPI. https://www.bls.gov/ppi/publications/price-adjustment-guide-for-contracting-parties.htm

## Priority: 4/5 — the core of every bid and the base already exists; bases by cost type, bond tiers, index-backed escalation and markup validation are cheap and directly affect margin.

## Sources
- https://github.com/ibericode/vat-rates
- https://www.bls.gov/developers/
- https://www.bls.gov/ppi/publications/price-adjustment-guide-for-contracting-parties.htm
- https://www.bls.gov/ppi/notices/2015/updated-inputs-to-industry-producer-price-indexes.htm
- https://destatis.de/EN/Service/OpenData/api-webservice.html
- https://correlaid.github.io/pystatis/pystatis.html
- https://www.avalara.com/blog/en/north-america/2026/05/avalara-mcp-servers.html
- https://gh.nn.ci/JoshMcMillen/avatax-mcp-server
- https://gritinsurance.com/bonds-surety/bond-cost-calculator
