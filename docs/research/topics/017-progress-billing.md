# 017. Progress billing / pay applications (G702/G703-style schedule of values) and retainage

## What it does
Contractors on lump-sum or unit-price jobs bill each month (or each milestone) against a **Schedule of Values (SOV)**. The SOV is the contract sum split into fixed line items. Every pay application records, per line: scheduled value, work completed in previous periods, work completed this period, materials stored, total to date, % complete, balance to finish and **retainage** held. A summary sheet (AIA G702 in the US) adds approved change orders, subtracts retainage and previous certificates, and gives the *current payment due*. The detail sheet is the G703 continuation sheet. Later steps include retainage reduction (for example 10% down to 5% at 50% complete), a retainage-release invoice at substantial completion, and lien waivers. Other regions use the same pattern: DE *Abschlagsrechnung* / *Schlussrechnung* (§ 632a BGB, § 16 VOB/B), and UK interim valuations with JCT retention.

## Already in the codebase (with file paths)
- `backend/app/modules/finance/models.py`: `Invoice` has a single flat `retention_amount`. `InvoiceLineItem` has quantity, rate, amount and `wbs_id`. There is **no** SOV entity, no period/application number, no previous-to-date accumulation, no % complete, no stored materials and no retainage-release logic.
- `backend/app/modules/us_pack/config.py`: `payment_application` describes the `AIA_G702_G703` field list (contract sum, change orders, retainage, current payment due, balance to finish). This is config metadata only. Nothing computes or renders it.
- `backend/app/modules/dach_pack/config.py`: `payment_templates` lists `ABSCHLAGSRECHNUNG` (with `retainage_pct`, `retainage_amount`) and `SCHLUSSRECHNUNG`, also config only.
- `backend/app/modules/changeorders/`, `boq/` and `full_evm/` hold the inputs (approved COs, BOQ positions, progress) but are not wired into billing.
- `reportlab` and `openpyxl` are already dependencies (`backend/pyproject.toml`), so PDF and Excel export need no new dependencies.
- Frontend: no pay-application UI (`frontend/src`).

**Gap:** the regional packs already name the data fields, but nothing models, calculates, validates or exports it.

## Who it helps and how much
- **Small GCs and subcontractors billing GCs or owners:** high value. Monthly pay apps are their main cash-flow event. Today they usually work from spreadsheets or paid add-ons, and arithmetic errors get the packet rejected.
- **Estimators:** the SOV can be generated straight from the awarded BOQ, so the estimate flows into billing without re-keying.
- **Owners' reps / QS:** certify amounts, track retainage held and released, and use the output as one input to over/under-billing (WIP) reports.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Build a new module `oe_progress_billing` (`backend/app/modules/progress_billing/`), with `depends=["oe_projects","oe_boq","oe_finance","oe_changeorders"]`.
- **Models:** `ScheduleOfValues` (per contract), `SOVLine` (links to a BOQ position or section, scheduled value, retainage %), `PayApplication` (number, period_to, status draft → submitted → certified → paid), `PayAppLine` (this-period completed, stored materials, retainage this period). Computed to-date values are snapshotted when the app is certified so history stays fixed.
- **Service:** "create next application" carries cumulative values forward. Approved change orders come in from a `changeorders` event, either as new SOV lines or as adjustments. Retainage rules (flat %, step-down at X% complete, per-line override) come from the regional pack config. A certified pay app emits an event that creates a receivable `finance.Invoice`, plus a separate retainage-release invoice later.
- **Validation rules** (CLAUDE.md requirement): sum of SOV lines = contract sum, to-date cannot exceed scheduled value without a CO, G703 totals must reconcile with the G702 summary, and a warning when retainage exceeds a configured jurisdiction cap.
- **Exports:** a G702/G703-*style* PDF (reportlab) and Excel export. AIA forms are copyrighted, so ship an original layout with equivalent columns and do not reproduce the AIA documents. Add DE Abschlagsrechnung and UK interim valuation templates through the packs.
- **AI hook:** `erp_chat/tools.py` gets read-only tools such as "what is due this period" and "retainage held by project". Any draft % complete values it suggests stay human-confirmed.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **ReportLab** (BSD), already used, for PDF rendering: https://www.reportlab.com/opensource/
- **openpyxl** (MIT), already used, for Excel SOV import and export: https://openpyxl.readthedocs.io/
- **Intuit QuickBooks Online MCP server** (official, local stdio, open source; sources conflict on Apache-2.0 vs MIT, so check the repo). It exposes invoice and estimate CRUD, which can push certified pay apps as invoices: https://github.com/intuit/quickbooks-online-mcp-server. QBO's built-in progress invoicing is documented for end users only. I could not verify any API field for progress billing or retainage.
- **Procore API**: payment application read endpoints exist under `rest/v1.0` (documented at developers.procore.com; the paid platform requires app registration). Relevant only for subs who bill GCs that use Procore. Write semantics are unverified.
- **Odoo AIA-style progress billing app**: the reference feature set is OPL-1, proprietary and paid, so it is not reusable: https://apps.odoo.com/apps/modules/18.0/construction_progress_billing_aia
- I found no OSI-licensed open-source SOV/retainage engine to reuse, so this would be built in-house.

## Priority: 5/5 — It is the cash-flow core for any contractor, the inputs (BOQ, COs, finance, pack configs) already exist, and the gap is one well-scoped module.

## Sources
- https://learn.aiacontracts.com/completing-g702-and-g703-forms/
- https://learn.aiacontracts.com/how-to-complete-the-g702-payment-application/
- https://www.autodesk.com/blogs/construction/g702-g703-forms-aia-billing/
- https://en-gb.support.procore.com/products/online/user-guide/project-level/invoicing/tutorials/create-an-invoice-for-release-of-retainage
- https://github.com/intuit/quickbooks-online-mcp-server
- https://glama.ai/mcp/servers/intuit/quickbooks-online-mcp-server
- https://quickbooks.intuit.com/ca/resources/updates/new-progress-invoicing-for-quickbooks-online
- https://apps.odoo.com/apps/modules/18.0/construction_progress_billing_aia
- https://www.foley.com/insights/publications/2025/11/no-more-10-retainage-california-mandates-5-retention-cap-on-private-constructi/
- https://www.bradley.com/insights/publications/2022/12/an-update-and-refresher-on-retainage
