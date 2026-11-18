# 016. Cash-flow forecasting and S-curves from schedule + cost loading

## What it does

It takes the priced BOQ (cost) and the schedule (time), assigns cost to activities ("cost loading"), and spreads each activity's cost across its dates using a distribution profile: linear, front-loaded, back-loaded, bell or S. The result is a monthly or weekly **outflow** curve and its cumulative **S-curve** (planned value baseline).

For a contractor, the outflow curve is only half the picture. The **inflow** side applies the commercial terms: billing frequency, retention/retainage %, payment lag (for example, paid 30-60 days after the pay application), advance payment and its recovery, and mobilisation. **Net cash position** = cumulative inflow − cumulative outflow. Its lowest point is the peak working-capital (overdraft) need. As work progresses, actual invoices and payments replace the forecast, and the curve is re-forecast over the remaining duration.

## Already in the codebase (with file paths)

A useful foundation already exists. The gap is mainly in how cost is spread and in the inflow side.

- `backend/app/modules/costmodel/models.py`: `CashFlow` table with fields `period` (YYYY-MM), `planned_inflow`, `planned_outflow`, `actual_inflow`, `actual_outflow` and their cumulative totals.
- `backend/app/modules/costmodel/service.py`:
  - `generate_budget_from_boq()` builds budget lines from the BOQ.
  - `generate_cash_flow_from_schedule()` spreads each budget line evenly (linear only) across its `period_start`/`period_end` months. It does **not** read schedule activities, and it sets `planned_inflow` to `"0"`, so there is no inflow model.
  - `get_s_curve()` builds the curve from EVM snapshots, with a fallback to cash-flow rows.
- `backend/app/modules/costmodel/router.py`: `GET /5d/s-curve`, `GET /5d/cash-flow`, `POST /5d/generate-cash-flow`.
- `backend/app/modules/full_evm/service.py`: `get_s_curve_data()` combines EVM snapshots with EAC/ETC forecasts.
- `backend/app/modules/schedule/models.py`: `Activity.boq_position_ids`, `WorkOrder.planned_cost`/`actual_cost`, and `ScheduleBaseline`. The data needed for true activity-based cost loading is already there. `schedule/router.py` also imports Primavera P6 XER.
- `backend/app/modules/finance/models.py`: `Invoice` with `due_date` and `retention_amount`, plus payments. These are the actual inflows and outflows.
- `frontend/src/features/costmodel/CostModelPage.tsx`: a hand-drawn SVG S-curve chart. Recharts is already a frontend dependency.

**Gaps:**
1. Cost loading is not done from `Activity` dates and BOQ links.
2. There are no distribution profiles.
3. There are no payment terms (retention, payment lag, advance), so no inflow forecast or net-cash/overdraft view.
4. Actuals from `finance` are not rolled into `CashFlow.actual_*`.
5. Baselines are not compared with the current forecast.
6. There is no portfolio-level cash view across projects.

## Who it helps and how much

- **Small general contractors and subcontractors:** high value. Cash, not margin, is what usually kills small contractors. Retention and a 45-day payment lag on a front-loaded trade can create a large overdraft early in the job. Seeing that before signing the contract is directly useful for bid/no-bid decisions, pricing finance costs and negotiating advance payments.
- **Estimators:** quick pre-tender cash forecasts are possible without a detailed schedule, using standard S-curves (the classic research approach).
- **Owners/developers:** a budget drawdown forecast for lenders.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)

**Medium.** All of this extends existing modules. No new heavy dependencies are needed (numeric spreading is a few lines of stdlib `Decimal` code).

1. **`costmodel`:** add a `curve_profiles` table using 5%-increment curve values, the same scheme P6 uses for resource curves. Seed it with the built-in shapes: linear, front, back, bell, double-bell and a beta/logistic S-curve. Also add a `payment_terms` JSONB field on the project or contract: billing period, retention %, retention release date, payment lag in days, advance % and its recovery rate.
2. **New service `build_cash_forecast(project_id, baseline_id=None)`:**
   - Walk `schedule.Activity` records, sum the linked BOQ position totals (or `WorkOrder.planned_cost`), and apply each activity's curve to produce weekly or monthly outflow.
   - Shift by billing period and payment lag, deduct retention and recover the advance to produce the inflow.
   - Compute net position and peak overdraft.
3. **Event subscriptions:** subscribe to `schedule.*` and `boq.*` events (via `core/events`) to flag the forecast as stale. Subscribe to `finance.invoice.*`/`payment.*` events to fill `actual_*`.
4. **Validation rules** (per the project rules): cost-loading coverage (BOQ total vs loaded total), activities without cost, cost outside the project dates, negative cash below a configurable threshold.
5. **Frontend:** a Recharts `ComposedChart` with outflow and inflow bars plus cumulative and net lines, a baseline overlay, and a "what-if" panel for payment terms.
6. **AI tool** (`erp_chat/tools.py`): "what is my peak overdraft if retention is 5% and the payment lag is 60 days?"

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)

- **Recharts** (MIT): already in `package.json`. https://www.npmjs.com/package/recharts
- **P6-style resource curves** (5% increments): a design reference for the profile format, so XER/P6 users can recognise it. https://tensix.com/primavera-p6-resource-curves/
- **Oracle curve profile definitions** (bell, back-loaded, double-bell). https://docs.oracle.com/cd/E80480_01/English/admin/app_admin_guide/93619.htm
- **MPXJ** (Java with a Python wrapper via JPype): reads MPP/XER/PMXML including cost data. It requires a JVM, which conflicts with the "lightweight" principle, so it is optional only. The license is reported as LGPL but listings conflict; check before bundling. https://github.com/joniles/mpxj
- **Xero MCP server** (official, MIT): pulls actual bills/invoices for small firms using Xero. https://github.com/XeroAPI/xero-mcp-server
- **QuickBooks Online MCP server** (Intuit, Apache-2.0, per directory listings; check the README): same purpose for QuickBooks users. https://github.com/intuit/quickbooks-online-mcp-server
- **Method references:** PMI paper on cash-flow forecasting and updating (Navon). https://www.pmi.org/learning/library/cash-flow-forecasting-updating-building-projects-2045
- I could not verify any open-source library or MCP server dedicated to construction cash-flow S-curves. The logic should be built in-house; it is small.

## Priority: 4/5 — Most data and endpoints already exist; activity-based loading plus retention/payment-lag inflow turns a linear demo into the cash view small contractors need most.

## Sources

- https://www.pmi.org/learning/library/cash-flow-forecasting-updating-building-projects-2045
- https://www.adventuresincre.com/development-budget-distributing-cash-flows-using-the-s-curve-method/
- https://tensix.com/primavera-p6-resource-curves/
- https://tensix.com/plotting-an-s-curve-cost-distribution-in-p6/
- https://docs.oracle.com/cd/E80480_01/English/admin/app_admin_guide/93619.htm
- https://help.elecosoft.com/powerproject/english/help/Content/HTML_Topics/Conceptual/Library_Explorer/Libraries/Resource_curves.htm
- https://github.com/joniles/mpxj
- https://pypi.org/project/mpxj/
- https://github.com/XeroAPI/xero-mcp-server
- https://github.com/intuit/quickbooks-online-mcp-server
- https://www.npmjs.com/package/recharts
