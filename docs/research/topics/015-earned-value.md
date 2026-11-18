# 015. Earned Value Management (CPI/SPI, EAC) for Small Contractors

## What it does
Earned Value Management (EVM) compares three numbers at a status date. Planned Value (PV) is the budget scheduled to date. Earned Value (EV) is the budget for the work actually done (BAC x % complete). Actual Cost (AC) is what was spent. From these it derives CV/SV, CPI = EV/AC, SPI = EV/PV, EAC (for example AC + (BAC - EV)/CPI), ETC, VAC and TCPI. For a small contractor, the useful version is simple: "are we making or losing money on this job, and what will it cost at the end?", updated monthly from data they already enter (BOQ, progress, invoices). They do not need ANSI-748 compliance reporting.

## Already in the codebase (with file paths)
The formula layer is mostly done. It exists in three places that overlap:
- `backend/app/modules/finance/service.py` (`create_evm_snapshot`): computes SV, CV, SPI, CPI, EAC, VAC, ETC and TCPI server-side, but from **manually entered** BAC/PV/EV/AC.
- `backend/app/modules/costmodel/service.py` (`calculate_evm`, `get_s_curve`, `generate_budget_from_boq`, `generate_cash_flow_from_schedule`, `create_what_if_scenario`): derives EV from the weighted `progress_pct` of schedule activities and AC from budget lines. Its docstring says PV is only approximated as `BAC x time_elapsed%`, with SPI clamped to [0, 5] and a TODO for a time-phased baseline.
- `backend/app/modules/full_evm/` (`manifest.py` says "enterprise", `auto_install=False`): adds CPI and SPI x CPI forecasts and S-curve data on top of the finance snapshots.
- Frontend: `frontend/src/features/costmodel/CostModelPage.tsx`, `frontend/src/features/finance/FinancePage.tsx`, and an ERP-chat renderer `frontend/src/features/erp-chat/full-page/right/renderers/CostModelRenderer.tsx`.

**Gap:**
1. There is no time-phased PV baseline (BOQ positions x activity planned dates, frozen as a baseline).
2. AC is not fed automatically from approved invoices, purchase orders, timesheets or an external accounting system.
3. There is no per-cost-code or per-trade EVM, so you cannot see which trade is bleeding.
4. There is no earned schedule (SPI(t)), even though standard SPI drifts back to 1.0 near the end of a job.
5. Three overlapping EVM implementations confuse users. They should be unified.
6. There are no validation rules for EVM inputs (EV > BAC, % complete going backwards, AC with no progress).

## Who it helps and how much
Owner-operators and project managers at 2–50 person general contractors and subcontractors (fit-out, MEP, civils). Most track job cost in spreadsheets or in their accounting software and find overruns only at closeout. A monthly CPI/EAC per job and per trade, built from data already in the ERP, is high value, but only if it needs almost no extra input. Formal EVM with control accounts and work packages is overkill for this audience and should stay optional.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.**
- Consolidate into `costmodel` as the single EVM engine. Make `finance` snapshots a stored output of it, and keep `full_evm` as an advanced add-on (earned schedule, multiple EAC methods).
- Add a `BaselinePV` table that is time-phased by week or month: BOQ budget lines spread across linked `schedule` activity planned dates.
- Subscribe through `app/core/events.py` to invoice-approved and PO-received events from `finance`/`procurement`, and to progress-updated events from `schedule`/`fieldreports`, so AC and EV refresh automatically.
- Add `boq_quality`-style ValidationRules (`evm.ev_exceeds_bac`, `evm.progress_regression`, `evm.ac_without_progress`).
- Expose an `get_project_evm` tool in `erp_chat/tools.py` so the assistant can answer "which jobs have CPI < 0.9?".
- Optional connector module: pull AC from QuickBooks Online or Xero by mapping accounting classes or tracking categories to cost codes.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **pmcontrols** (Python, MIT, v0.2.1, released June 2026, so young): EVM indices, EAC methods, TCPI, and Lipke earned schedule (ES, SPI(t), IEAC(t)). https://github.com/arikanatakan/pmcontrols. It could serve as a reference or test oracle. The formulas are simple enough to keep in-house with `Decimal`.
- **Earned Schedule reference and calculator** (free): https://www.earnedschedule.com/Calculator.shtml
- **Intuit QuickBooks Online MCP server** (official, MIT, local stdio, OAuth via the Intuit Developer Portal): https://github.com/intuit/quickbooks-online-mcp-server. Reads bills, invoices and reports for AC. The QBO API needs a free developer account; the customer pays for the QBO subscription.
- **Xero MCP server** (official, MIT, npm `@xeroapi/xero-mcp-server`): https://github.com/XeroAPI/xero-mcp-server. Covers invoices, bank transactions and P&L. Xero is also reported to run a hosted endpoint; I could not verify its exact scope.
- **PMI EVM overview** (methodology reference): https://www.pmi.org/blog/earned-value-management
- I found no construction-specific open-source EVM MCP server and could not verify that one exists.

## Priority: 4/5 — Formulas already exist. Auto-fed AC/EV plus a real time-phased PV turn them into the "am I losing money on this job" signal small contractors lack, at medium cost.

## Sources
- https://www.pmi.org/blog/earned-value-management
- https://www.earnedschedule.com/Calculator.shtml
- https://www.pmi.org/learning/library/practical-calculation-schedule-variance-7028
- https://pypi.org/project/pmcontrols/
- https://github.com/arikanatakan/pmcontrols
- https://github.com/intuit/quickbooks-online-mcp-server
- https://glama.ai/mcp/servers/intuit/quickbooks-online-mcp-server
- https://github.com/XeroAPI/xero-mcp-server
- https://monograph.com/blog/earned-value-management-engineering-firms
