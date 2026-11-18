# 014. 5D cost control: budget vs committed vs actual cost tracking

## What it does
This tracks each cost code or WBS line through four numbers:
- **Budget**: the original budget plus approved changes, which gives the revised budget.
- **Committed**: signed subcontracts, purchase orders and approved change orders.
- **Actual**: invoices received or paid, plus direct costs.
- **Forecast at completion**: the expected final cost.

From these it derives **remaining budget**, which is revised budget minus committed minus uncommitted actuals, and **projected over/under**. Lines that go negative turn red. This is the core screen in commercial construction cost control. Procore's Budget tool is one example: commitments are subcontracts and POs in approved status, and over/under is projected budget minus estimated cost at completion. For a small contractor, the real value is that these numbers fill in **automatically** from POs, change orders and invoices, so nobody keeps them by hand in a spreadsheet.

## Already in the codebase (with file paths)
The data model is mostly there. What is missing is the automatic flow of data into it.
- `backend/app/modules/costmodel/models.py` has `BudgetLine` with `planned_amount`, `committed_amount`, `actual_amount` and `forecast_amount` (money stored as strings), plus `CostSnapshot` (BCWS/BCWP/ACWP, CPI/SPI) and `CashFlow`. Aggregation lives in `costmodel/repository.py` and `costmodel/service.py`.
- `backend/app/modules/finance/models.py` has a second, parallel `ProjectBudget` with `original_budget`, `revised_budget`, `committed`, `actual` and `forecast_final` (Decimal `MoneyType`), plus `Invoice`, `Payment` and `EVMSnapshot`.
- `backend/app/modules/procurement/repository.py` already computes "total committed" as the sum of non-cancelled POs. It is not written back to any budget line, and procurement publishes no events.
- `backend/app/modules/full_evm/models.py` has `EVMForecast` (ETC/EAC/VAC/TCPI).
- `backend/app/modules/changeorders/service.py` publishes events, but no module listens to them for budget revision.
- On the frontend, `frontend/src/features/costmodel` and `frontend/src/features/finance` exist.

**Gap:**
1. There are two budget tables, and they overlap.
2. Committed and actual values are entered by hand. Approved POs, subcontracts and COs do not roll up into committed, and posted invoices do not roll up into actual.
3. There is no shared cost-code key across BOQ, PO lines and invoice lines.
4. There is no import of actuals from accounting tools (QuickBooks/Xero).
5. There are no validation rules, for example "PO exceeds remaining budget" or "invoice without commitment".

## Who it helps and how much
- **Small general contractors and fit-out firms:** high value. Margin fade, where costs creep up unnoticed until the job is losing money, is the main way small jobs lose money. A live view of budget vs committed vs actual for each cost code replaces a weekly spreadsheet reconciliation.
- **Estimators:** medium value. Closed-out actuals feed back into future rates.
- **Owners and bookkeepers:** medium value. Accounting stays the system of record for actuals, and the ERP adds the job-cost view that a general ledger cannot give.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Modules touched: `costmodel` (the canonical budget ledger), `finance`, `procurement`, `changeorders`, `boq`, `validation`, and optionally `integrations`.
1. **Merge the budget tables.** Make `finance.ProjectBudget` (Decimal) the single ledger, with `costmodel` reading from it. Add a `cost_code` field (DIN 276 / NRM / MasterFormat via the regional packs) to BOQ positions, PO items and invoice lines.
2. **Roll costs up through events.** Procurement should publish `procurement.po.approved` and `procurement.po.cancelled`. Changeorders should publish `changeorder.approved`, which raises revised budget on the owner side or commitment on the subcontract side. Finance should publish `finance.invoice.posted`. A subscriber in `costmodel` recalculates the affected lines inside the transaction and writes an audit entry.
3. **Seed the budget.** Add a "freeze BOQ as budget" action, which already partially exists in costmodel's generate-from-BOQ endpoint.
4. **Add validation rules.** Put them in `core/validation/rules`: `cost.commitment_exceeds_budget`, `cost.invoice_without_commitment` and `cost.negative_remaining`. These feed the traffic-light dashboard.
5. **Import actuals from accounting (optional).** An `integrations` sub-module pulls bills and expenses tagged to a project from QuickBooks Online (CustomerRef/ClassRef) or Xero (tracking categories). The user maps them to cost codes and confirms them before they count as actuals.
6. **Add an `erp_chat` tool.** A `get_budget_status(project)` tool, so the AI can answer "which cost codes are over budget?"

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **QuickBooks Online Accounting API** (https://developer.intuit.com/app/developer/qbo/docs/get-started). Bill and Purchase lines carry CustomerRef/ClassRef and a billable status, which is what job costing needs. Free developer sandbox; production apps use OAuth 2.0.
- **intuit/quickbooks-online-mcp-server** (https://github.com/intuit/quickbooks-online-mcp-server). Official MCP server from Intuit; runs locally over stdio. Sources disagree on the license (Apache-2.0 or MIT), so check the LICENSE file. Good for AI-assisted reconciliation, not for the core sync.
- **python-quickbooks** (https://github.com/ej2/python-quickbooks). MIT-licensed Python SDK for the QBO API.
- **Xero Accounting API, tracking categories** (https://developer.xero.com/documentation/api/accounting/trackingcategories). Projects and jobs are commonly tagged through tracking categories.
- **XeroAPI/xero-mcp-server** (https://github.com/XeroAPI/xero-mcp-server). Official MCP server from Xero, with tools to list, create and update tracking categories. MIT, per the repo.
- **xero-python** (https://github.com/XeroAPI/xero-python). Official Python SDK, MIT.
- No new dependencies are needed for the core roll-up: the existing event bus, SQLAlchemy and Decimal are enough.

## Priority: 5/5 — the data model already exists, so wiring POs, change orders and invoices into an automatic budget/committed/actual ledger is a medium-effort change with the highest day-to-day value for small contractors.

## Sources
- https://support.procore.com/products/online/user-guide/project-level/budget/tutorials/about-the-procore-standard-budget-view
- https://v2.support.procore.com/product-manuals/budget-project/tutorials/read-a-budget
- https://github.com/intuit/quickbooks-online-mcp-server
- https://glama.ai/mcp/servers/intuit/quickbooks-online-mcp-server
- https://developer.intuit.com/app/developer/qbo/docs/get-started
- https://cdn.cdata.com/help/RNN/odbc/pg_table-billlineitems.htm
- https://developers.apideck.com/apis/accounting/quickbooks/gotchas
- https://github.com/XeroAPI/xero-mcp-server
- https://cdn.jsdelivr.net/gh/XeroAPI/xero-mcp-server@main/README.md
- https://developer.xero.com/documentation/api/accounting/trackingcategories
- https://github.com/ej2/python-quickbooks
- https://github.com/XeroAPI/xero-python
