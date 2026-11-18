# 038. Payroll connectors (Gusto, ADP, Paychex, Deel; unified APIs like Merge/Finch)

## What it does
Two-way links between the ERP and a payroll provider:
- **Outbound (hours to payroll):** crew hours that are already logged on site (daily reports, by trade/WBS) get pushed as timesheets, so office staff stop re-typing hours.
- **Inbound (cost to job):** gross pay, employer taxes and burden come back from processed payrolls and are posted as actual labor cost per project or WBS. Earned-value and cost-model actuals then match what was really paid.
- **Rates:** loaded labor rates (wage plus burden) come from real payroll data and feed estimating assemblies.

## Already in the codebase (with file paths)
- `backend/app/modules/fieldreports/models.py`: `SiteWorkforceLog` (`oe_fieldreports_workforce`) stores headcount, `hours_worked`, `overtime_hours`, `wbs_id` and `cost_category` per trade/company. This is the natural data source, but it is crew-level, not per-employee.
- `backend/app/modules/costmodel/models.py`: has a `labor` cost category for actuals.
- `backend/app/modules/finance/` and `backend/app/modules/full_evm/` are where actual cost lands.
- `backend/app/modules/integrations/` only covers messaging (Slack, Teams, Telegram, WhatsApp, Discord, email). It has no HR or payroll client.
- **Gap:** a search for payroll, Gusto, Paychex, Finch and timesheet found nothing. There is no employee or timesheet entity, no wage or burden import, and no US certified-payroll (WH-347) support in `us_pack`.

## Who it helps and how much
The main beneficiary is a small self-performing contractor (5–50 field staff) on Gusto, ADP or Paychex. It saves a few hours per pay period of double entry, and job costing becomes accurate without anyone keying in labor costs.
- Estimating-only firms gain little; at most, real loaded rates.
- Deel matters mainly for firms using international contractors.

Overall value is Medium. It is useful but secondary to estimating, and it needs per-employee time capture that the ERP does not yet have.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium–Large.** Recommended path:
1. **New module `oe_payroll_connector`** (`manifest.py` with `depends=["oe_fieldreports", "oe_costmodel"]`). It adds models `PayrollConnection`, `EmployeeLink` and `TimesheetExport`, and a provider-adapter interface with `push_timesheets` / `pull_payroll_costs`.
2. **Adapters:** one unified-API adapter (Finch or Merge) covers ADP, Paychex, Gusto and others in a single integration. A direct Gusto adapter is optional, since Gusto has the most open small-business API.
3. **Event hook:** on the field-report-approved event, build a draft timesheet. Following the "human-confirmed" principle, the user reviews it before it is pushed.
4. **Validation rules:** hours above a daily cap, a WBS code is missing, an employee is unmapped, overtime does not match the total.
5. **Inbound:** a scheduled pull of payroll journal lines turns them into costmodel actuals.

**Blockers:**
- Per-worker time entries (an extension of `SiteWorkforceLog`).
- OAuth app approval with each vendor. ADP, Paychex and Gusto all gate production keys behind a partner program.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Gusto Time Tracking API** (OAuth2, `time_sheets` endpoints). Free for approved app partners; production keys go through Gusto partner approval. https://docs.gusto.com/app-integrations/docs/syncing-time-tracking-data
- **Gusto official hosted MCP server**, which reads and writes payroll data (writes require confirmation). This needs a Gusto account. https://gusto.com/product/integrations/gusto-mcp
- **ADP Workforce Now API Central:** Time/Attendance APIs read and update timecards. Each customer must buy the paid API Central add-on, and developers must join the partner program. https://apps.adp.com/en-US/apps/410612/ADP%C2%AE-API-Central-for-ADP-Workforce-Now%C2%AE/features
- **Paychex Flex REST API** (workers, payroll, time). Partner review is required, and the customer must approve the link. https://developer.paychex.com
- **Deel API:** timesheets for pay-as-you-go contractors (`POST /rest/v2/timesheets`, bearer token). https://developer.deel.com/docs/manage-contractor-timesheets
- **Finch:** unified API covering 250+ HRIS/payroll systems. It claims write support for deductions. Paid: a third-party tracker lists a Starter plan at about $65/mo; higher tiers are not public. Finch also publishes an MCP server. https://tryfinch.com/pricing, https://www.tryfinch.com/blog/finch-mcp-server
- **Merge HRIS:** unified API for employees, payroll runs, time off and timesheets. Contract pricing; I could not verify list prices. I also could not confirm an official Merge payroll MCP server. https://docs.merge.dev/hris/
- **Open source:** I found no maintained OSS unified payroll SDK. Plain `httpx` with OAuth2 (Authlib, BSD) is enough.

## Priority: 2/5 — valuable for self-performing contractors, but it needs per-worker time capture first and is gated by vendor partner programs; build it after core estimating, BOQ and cost actuals mature, starting with one unified-API adapter.

## Sources
- https://docs.gusto.com/app-integrations/docs/syncing-time-tracking-data
- https://gusto.com/product/integrations/gusto-mcp
- https://apps.adp.com/en-US/apps/410612/ADP%C2%AE-API-Central-for-ADP-Workforce-Now%C2%AE/features
- https://supergood.ai/api-report-card/paychex-flex
- https://developer.deel.com/docs/manage-contractor-timesheets
- https://tryfinch.com/pricing
- https://pricingsaas.com/companies/tryfinch
- https://www.tryfinch.com/blog/finch-mcp-server
- https://docs.merge.dev/hris/
- https://merge.dev/blog/finch-api-pricing
