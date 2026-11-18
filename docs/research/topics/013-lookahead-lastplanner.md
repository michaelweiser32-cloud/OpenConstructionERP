# 013. Look-ahead Planning and Last Planner System (weekly work plans, PPC)

## What it does
The Last Planner System (LPS), described by the Lean Construction Institute (LCI), adds short-term planning layers under the master schedule: phase or pull planning, a rolling **look-ahead** (usually 3 to 6 weeks) in which constraints such as design, materials, permits, labor, prerequisite work and inspections are found and cleared, a **weekly work plan (WWP)** of tasks the foremen commit to, and a weekly review. **Percent Plan Complete (PPC)** is completed commitments divided by planned commitments. Each missed commitment gets a standard **reason for variance** (RFV) so recurring causes can be fixed.

## Already in the codebase (with file paths)
- `backend/app/modules/schedule/models.py`: `Schedule`, `Activity` (CPM fields, `is_critical`, MS Project-style `constraint_type`/`constraint_date`, date-type only), `WorkOrder` (activity-linked, assignee, planned and actual dates, status), `ScheduleBaseline`, `ProgressUpdate` (percent progress with draft, submitted and approved states).
- `backend/app/modules/tasks/models.py`: generic `Task` with responsible person, due date, `depends_on`, `meeting_id`, status and checklist.
- `backend/app/modules/meetings/models.py`: `Meeting` with `meeting_type` and `action_items`.
- Frontend: `frontend/src/features/schedule`, `tasks`, `meetings`; `recharts` is already a dependency.
- **Gap:** there is no look-ahead window or view, no constraint log with a readiness state, no weekly commitment entity, no PPC calculation or trend, and no RFV taxonomy.

## Who it helps and how much
- **Small GCs and trade contractors running 2 to 10 jobs:** a weekly plan with PPC is the cheapest way to make planning reliable without a full-time scheduler.
- **Estimators and owners:** RFV history (for example, materials late or the prior trade not finished) feeds risk allowances and productivity assumptions in later estimates.
- IGLC research reports that higher PPC goes with higher productivity. PPC can still hide variability, so pair it with schedule and EVM metrics.
- Value: **Medium-High**. Commercial LPS tools (Touchplan, Outbuild, vPlanner) are mostly quote-priced for larger GCs.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** This fits as a new module `oe_lean_planning` with `depends=["oe_schedule", "oe_tasks", "oe_projects"]`, or as a sub-package of `schedule`.
- Models: `LookaheadWindow` (project, start week, weeks), `Constraint` (activity_id, type enum, owner, need-by date, status open or cleared, or links to an existing `Task`, RFI or submittal), `WeeklyWorkPlan` (project, ISO week, status draft, committed or closed), `Commitment` (activity_id or work_order_id, trade or contact, planned qty, done bool, `rfv_code`, note), and `PPCSnapshot`.
- Service: build the look-ahead from `Activity` rows whose dates fall in the window; flag an activity "ready" only when it has no open constraints; close the week to compute PPC and RFV Pareto.
- Events: on `rfi.closed` or `procurement.delivered`, auto-clear the linked constraint. Emit `lean.week_closed` so the `notifications` and `integrations` modules (Slack, Teams, WhatsApp) can post PPC.
- Validation rules (required by the project rules): commitment without an assignee; committed task with open constraints; RFV missing on an incomplete commitment; PPC below a threshold, as a warning.
- Frontend: a look-ahead board (weeks by trade), a constraint log table, a WWP checklist that works on mobile, and PPC and RFV charts in recharts. RFV labels via i18n.
- `erp_chat` tool: "What is blocking next week?"; AI-suggested RFV from field report text, confirmed by the user.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **LCI LPS standard work and Reasons for Variance PDFs**: free public reference for the RFV taxonomy and process. https://leanconstruction.org/wp-content/uploads/2022/08/12_LPS_Reasons_For_Variance.pdf
- **Procore Lookaheads API** (`/rest/v1.x/projects/{id}/schedule/lookaheads` and `lookahead_tasks`): proprietary, needs a Procore account; useful for import and export. Endpoints were verified only through third-party SDK docs (hexdocs `procore_sdk`), not on developers.procore.com.
- **procore-mcp-server** (community, TylerIlunga): exposes show and create lookahead tools. Unaudited.
- **jeffersonbim/lean-planning-mcp** (GitHub, MIT, about 9 stars): described as an MCP server that adds Last Planner System and AWP layers on top of MS Project, P6 and Synchro schedules. I could not read the README (access blocked), so its scope is **unverified**.
- **recharts** (MIT, already in the frontend) for the PPC trend and RFV Pareto charts.
- No mature open-source LPS application was found.

## Priority: 3/5 — clear gap and reuses existing schedule, tasks and meetings models, but it is a planning and site feature rather than core estimating

## Sources
- https://leanconstruction.org/wp-content/uploads/2022/08/12_LPS_Reasons_For_Variance.pdf
- https://leanconstruction.org/wp-content/uploads/2023/10/2023_LCI_LeanConstructionPlannerStandard-Work.pdf
- https://leanconstruction.org/lean-construction-journal/doi-info-2019-131-146/
- https://iglc.net/Papers/Details/1788
- https://hexdocs.pm/procore_sdk/Procore.Api.ProjectManagementProjectScheduleLookaheads.html
- https://glama.ai/mcp/servers/TylerIlunga/procore-mcp-server/tools/show_lookahead
- https://github.com/jeffersonbim/lean-planning-mcp
- https://www.outbuild.com/blog/last-planner-software
- https://www.selecthub.com/p/construction-management-software/touchplan/
