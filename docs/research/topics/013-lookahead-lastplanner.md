# 013. Look-ahead Planning and Last Planner System (weekly work plans, PPC)

## What it does
The Last Planner System (LPS), described by the Lean Construction Institute (LCI), adds short-term planning layers under the master schedule: phase or pull planning, a rolling **look-ahead** (usually 3 to 6 weeks) in which constraints such as design, materials, permits, labor, prerequisite work and inspections are found and cleared, a **weekly work plan (WWP)** of tasks the foremen commit to, and a weekly review. **Percent Plan Complete (PPC)** is completed commitments divided by planned commitments. Each missed commitment gets a standard **reason for variance** (RFV) so recurring causes can be fixed. A short version for small firms is "Should, Can, Will, Did".

## Already in the codebase (with file paths)
- `backend/app/modules/schedule/models.py`: `Schedule`, `Activity` (CPM fields, `is_critical`, MS Project-style `constraint_type`/`constraint_date`, which are date constraints and not LPS readiness constraints), `WorkOrder` (activity-linked, assignee, planned and actual dates, status), `ScheduleBaseline`, `ProgressUpdate` (percent progress with draft, submitted and approved states).
- `backend/app/modules/tasks/models.py`: generic `Task` with responsible person, due date, `depends_on`, `meeting_id`, status and checklist. This is a reasonable base for constraint items.
- `backend/app/modules/meetings/models.py`: `Meeting` with `meeting_type` and `action_items`, so a weekly coordination meeting can be recorded.
- `backend/app/modules/fieldreports/models.py`: daily reports and workforce logs, which can show what was actually done.
- Frontend: `frontend/src/features/schedule`, `tasks`, `meetings`; `recharts` is already a dependency.
- **Gap:** there is no look-ahead window or view, no constraint log with a readiness state, no weekly commitment entity, no PPC calculation or trend, and no RFV taxonomy. A grep for lookahead, Last Planner and PPC finds nothing in the backend modules.

## Who it helps and how much
- **Small GCs and trade contractors running 2 to 10 jobs:** a weekly plan with PPC is the cheapest way to make planning reliable without a full-time scheduler. It replaces whiteboards, sticky notes and spreadsheets.
- **Estimators and owners:** RFV history (for example, materials late or the prior trade not finished) feeds risk allowances and productivity assumptions in later estimates.
- IGLC research reports that higher PPC goes with higher productivity. Other IGLC papers warn that PPC can stay high while variability is hidden, so PPC should sit next to schedule and earned value metrics, not replace them.
- Value: **Medium-High**. Commercial LPS tools such as Touchplan, Outbuild and vPlanner are mostly sold by quote to larger GCs, which leaves small firms underserved.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** This fits as a new module `oe_lean_planning` with `depends=["oe_schedule", "oe_tasks", "oe_projects"]`, or as a sub-package of `schedule`.
- Models: `LookaheadWindow` (project, start week, weeks), `Constraint` (activity_id, type enum, owner, need-by date, status open or cleared, or links to an existing `Task`, RFI or submittal), `WeeklyWorkPlan` (project, ISO week, status draft, committed or closed), `Commitment` (activity_id or work_order_id, trade or contact, planned qty, done bool, `rfv_code`, note), and `PPCSnapshot`.
- Service: build the look-ahead from `Activity` rows whose dates fall in the window; flag an activity "ready" only when it has no open constraints; close the week to compute PPC and an RFV Pareto.
- Events: on `rfi.closed` or `procurement.delivered`, auto-clear the linked constraint. Emit `lean.week_closed` so the `notifications` and `integrations` modules (Slack, Teams, WhatsApp) can post PPC.
- Validation rules (required by the project rules): commitment without an assignee; committed task with open constraints; RFV missing on an incomplete commitment; PPC below a threshold, as a warning.
- Frontend: a look-ahead board (weeks by trade), a constraint log table, a WWP checklist that works on mobile, and PPC and RFV charts in recharts. i18n RFV labels, following LCI's standard list.
- AI and `erp_chat` tools: a "What is blocking next week?" tool and a suggested RFV classification from field report text. The user confirms each suggestion.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **LCI LPS standard work and Reasons for Variance PDFs**: free public reference for the RFV taxonomy and process. https://leanconstruction.org/wp-content/uploads/2022/08/12_LPS_Reasons_For_Variance.pdf
- **Procore Lookaheads API** (`/rest/v1.x/projects/{id}/schedule/lookaheads` and `lookahead_tasks`): proprietary, needs a Procore account; useful for import and export. Endpoints were verified only through third-party SDK docs (hexdocs `procore_sdk`), not on developers.procore.com.
- **procore-mcp-server** (community, TylerIlunga): exposes show and create lookahead tools. Third-party and unaudited.
- **jeffersonbim/lean-planning-mcp** (GitHub, MIT, about 9 stars): described as an MCP server that adds Last Planner System and AWP layers on top of MS Project, P6 and Synchro schedules. I could not read the README (access blocked), so its scope is **unverified**.
- **recharts** (MIT, already in the frontend) for the PPC trend and RFV Pareto charts. No new backend dependency is needed; PPC is simple arithmetic.
- No mature open-source LPS application was found. GitHub has only small student and hobby repos with no license.

## Priority: 3/5 — clear gap and reuses existing schedule, tasks and meetings models, but it is a planning and site feature rather than core estimating
Moderate effort and a good fit for small firms that cannot justify quote-priced lean SaaS. It ranks below core estimating, BOQ and tender features for an estimating-first product.

## Sources
- https://leanconstruction.org/wp-content/uploads/2022/08/12_LPS_Reasons_For_Variance.pdf
- https://leanconstruction.org/wp-content/uploads/2022/08/1_LPS_Introduction_Principles.pdf
- https://leanconstruction.org/wp-content/uploads/2023/10/2023_LCI_LeanConstructionPlannerStandard-Work.pdf
- https://leanconstruction.org/lean-construction-journal/doi-info-2019-131-146/
- https://p2sl.berkeley.edu/?p=200
- https://iglc.net/Papers/Details/1788
- https://hexdocs.pm/procore_sdk/Procore.Api.ProjectManagementProjectScheduleLookaheads.html
- https://hexdocs.pm/procore_sdk/Procore.Api.ProjectManagementProjectScheduleLookaheadTasks.html
- https://glama.ai/mcp/servers/TylerIlunga/procore-mcp-server/tools/show_lookahead
- https://github.com/jeffersonbim/lean-planning-mcp
- https://www.outbuild.com/blog/last-planner-software
- https://www.selecthub.com/p/construction-management-software/touchplan/
