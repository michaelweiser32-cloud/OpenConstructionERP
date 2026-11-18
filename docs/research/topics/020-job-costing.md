# 020. Job costing and cost-to-complete forecasting

## What it does
Job costing tracks, per job and per cost code (budget line), four numbers: **budget** (original plus approved changes), **committed** (signed POs and subcontracts), **actual** (posted bills, labour hours times rate, equipment), and **forecast to complete** (FTC/ETC). Projected cost at completion = actual + open commitments + uncommitted FTC; projected over/under = revised budget minus projected cost. Commercial tools such as Procore let the project manager pick an FTC method per line: automatic (keep variance at zero), manual lump sum, itemised, or time-based "monitored resources" that draw down over the duration. EVM formulas (EAC = AC + (BAC - EV)/CPI) sit on top as a cross-check, but on a small job the PM's line-by-line judgement drives the forecast.

## Already in the codebase (with file paths)
A lot of the data model is already there, spread over three modules that overlap:
- `backend/app/modules/costmodel/models.py`: `BudgetLine` (planned, committed, actual and forecast amounts per BOQ position or activity, plus a category), `CostSnapshot` (BCWS/BCWP/ACWP, forecast_eac) and `CashFlow`. `costmodel/service.py` has `generate_budget_from_boq`, `calculate_evm`, `get_variance`, `create_what_if_scenario` and S-curve/cash-flow generation from the schedule.
- `backend/app/modules/finance/models.py`: `ProjectBudget` (original, revised, committed, actual, forecast_final per WBS/category), `Invoice`, `Payment` and `EVMSnapshot` (EAC/ETC).
- `backend/app/modules/full_evm/service.py`: `calculate_forecast` (CPI and SPI*CPI ETC, VAC, TCPI) based on the latest finance snapshot.

**Gaps:** (1) Nothing subscribes to events that would roll up committed/actual amounts. A grep finds no event subscriptions in costmodel, finance or full_evm, so procurement POs, subcontracts, approved change orders and finance invoices do not update `BudgetLine` or `ProjectBudget`. Those numbers have to be typed in by hand. (2) Two budget tables (`BudgetLine` and `ProjectBudget`) duplicate each other and should be reconciled. (3) There is no per-line FTC method (auto, lump sum or monitored) and no forecast history or audit trail. (4) There is no labour or equipment time capture feeding actual cost; timesheet hits appear only in `costs/router.py` and `schedule/service.py`. (5) There is no accounting sync (QuickBooks or Xero), and that is where small firms' actual costs really live. (6) There are no validation rules such as "actual > budget with no CO" or "committed > budget".

## Who it helps and how much
High value for small general contractors and trade subcontractors. Their usual pain is finding out a job lost money only after it closed. A weekly cost-to-complete review on 20-50 cost codes is the main control habit that separates profitable small contractors from the rest. It also closes the loop for estimators: actual unit costs can feed the next estimate (`costs`/`assemblies`). Because the models already exist, wiring them together costs far less than the value it delivers.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Merge onto one budget-line model (keep `costmodel.BudgetLine` and treat `finance.ProjectBudget` as a view or migrate it away), keyed by cost code (`boq_position_id` / classification).
- `costmodel/events.py`: subscribe to `procurement.po.approved`, `changeorders.approved`, `finance.invoice.posted` and `fieldreports.labour_logged` via `app/core/events.py`, and update committed, actual and revised budget amounts.
- Add `ftc_method` and `ftc_amount` to the line, plus a `ForecastRevision` table (period, user, note) recorded through core audit.
- Add an endpoint `GET /costmodel/{project}/job-cost-report` with budget, committed, actual, FTC, projected and variance columns.
- `validators.py`: rule set `job_cost_quality` (overrun without CO, committed > revised budget, stale forecast older than 30 days).
- Optional plugin module `oe_accounting_sync` to pull bills and time from QuickBooks or Xero, mapping Class or Tracking Category to job and cost code.
- Frontend: an AG Grid job-cost sheet with an editable FTC column; `erp_chat/tools.py` gets a tool that answers "which jobs are trending over?"

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Intuit QuickBooks Online MCP server**, the official repo (https://github.com/intuit/quickbooks-online-mcp-server). Covers Customer, Bill, Purchase, Class, Time Activity and Estimate. The repo page lists both MIT and Apache-2.0, so check the LICENSE file. It needs a QBO subscription and the free Intuit developer app.
- **QuickBooks Online Accounting API** (https://developer.intuit.com/app/developer/qbo/docs/get-started). Job costing uses sub-customers as jobs, plus Class and TimeActivity. API access is free and the QBO plan is paid.
- **Xero official MCP server** (https://github.com/XeroAPI/xero-mcp-server), MIT. It has tracking-category and payroll-timesheet tools but **no Projects tools** (verified on the repo page).
- **Xero Projects API** (base `https://api.xero.com/projects.xro/2.0`, see https://central.ballerina.io/ballerinax/xero.projects/1.5.0). Covers projects, tasks, time and expenses. Xero Projects is a paid add-on.
- **ERPNext** (https://github.com/frappe/erpnext, GPL-3.0), a reference design for project costing from timesheets, purchases and expense claims. Use it as design reference only; do not copy code because of the licence mix.
- Python stdlib `decimal` covers the arithmetic, so no new dependency is needed.

## Priority: 5/5 — models already exist; wiring events plus an FTC column turns three dormant modules into the core weekly control a small contractor needs.

## Sources
- https://v2.support.procore.com/process-guides/owner-financial-management-user-guide/forecast-to-complete
- https://support.procore.com/faq/which-calculation-method-should-i-choose-when-using-the-forecast-to-complete-feature
- https://support.procore.com/faq/how-does-the-budget-forecast-report
- https://github.com/intuit/quickbooks-online-mcp-server
- https://developer.intuit.com/app/developer/qbo/docs/get-started
- https://github.com/XeroAPI/xero-mcp-server
- https://central.ballerina.io/ballerinax/xero.projects/1.5.0
- https://www.xero.com/us/projects/
- https://github.com/frappe/erpnext
