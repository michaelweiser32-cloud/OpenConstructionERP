# 010. Estimate review/approval workflow and automated estimate QA rules

## What it does
Before an estimate goes out as a bid, it goes through a short gated flow: Draft, then Self-check, then Peer/Senior review, then Approved (locked), then Submitted. Automated QA rules run at each gate. They catch zero rates, missing quantities, duplicate items, rates outside the benchmark band, missing markup or contingency, stale cost data, uncovered trades and lump-sum overuse. A failing ERROR rule blocks approval. A WARNING needs a reviewer comment or a waiver. The approved revision is frozen and stamped with the approver, time and validation score.

## Already in the codebase (with file paths)
- **BOQ status and lock**: `backend/app/modules/boq/models.py` has `status`, `is_locked`, `approved_by` and `approved_at`. `POST /boqs/{id}/lock/` in `backend/app/modules/boq/router.py` sets `approved_by` to the current user. It does not check validation results and has no multi-step review.
- **Generic approvals**: `backend/app/modules/enterprise_workflows/` holds `ApprovalWorkflow` and `ApprovalRequest` keyed by `entity_type`/`entity_id`, with approve, reject and cancel endpoints. A grep found no other module referencing it, and no event links it to the BOQ lock.
- **Workflow primitives**: `backend/app/core/workflow_engine.py` provides ball-in-court, steps and due dates. It is used by RFI, Submittals and NCR.
- **QA rules**: `backend/app/core/validation/rules/` has about 30 rules, including `boq_quality.*` (zero rates, quantities, duplicates, `rate_vs_benchmark`, `lump_sum_ratio`, `cost_concentration`, `total_mismatch`), plus `din276.*`, `gaeb.*`, `nrm.*` and `masterformat.*`.
- **Review UI pieces**: `frontend/src/features/boq/` has `PriceReviewPanel.tsx`, `CommentDrawer.tsx` and `VersionHistoryDrawer.tsx`.

**Gap:** the parts are there, but nothing connects them into one review flow. Specifically:
1. Approval is not gated on the validation report.
2. Approval steps are not configurable per company, for example "over $250k needs owner sign-off".
3. A few QA rules are missing: markup/overhead/profit/contingency present and within range, cost data age, trade coverage against a project-type template, bid-day subcontractor quote coverage, and the rate change from the last approved revision.
4. Warnings cannot be waived with a reason.
5. There is no "Review" inbox and no notifications.

## Who it helps and how much
- **Small general contractors and estimating shops with 1 to 5 estimators**: high value. Most bid-day losses come from clerical errors, such as a missing scope, a zero rate or a forgotten markup. An automated pre-submit gate is cheap insurance, and an owner sign-off is the main control a small firm needs.
- **Solo estimators**: medium value, from the self-check gate alone.
- Commercial tools offer this only in a basic form. For example, ProEst lets users email proposals to stakeholders for review and approval. So a rule-driven gate is a differentiator.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Modules touched: `boq`, `enterprise_workflows`, `validation`, `notifications`, plus the frontend `boq` feature.
- Add an `estimate_review` rule set in `core/validation/rules/` with the new rules listed under Gap point 3. Thresholds are configurable per tenant.
- Add a hook in `boq`: `boq.before_lock` runs the validation engine. It blocks on ERROR and requires a waiver (reason and user) for each WARNING.
- Have `enterprise_workflows` subscribe to `boq.submitted_for_review` through `core/events.py`. It then creates an `ApprovalRequest` using conditional steps. The conditions could use JSON rules on the total, margin or project type, and could be evaluated by GoRules ZEN, which is optional. When the final approval event fires, the BOQ is locked and a revision snapshot is taken.
- Have `notifications` and `integrations` (email, Slack, Teams) send "estimate awaiting your review".
- Add an `erp_chat/tools.py` tool, `review_estimate(boq_id)`, so the AI summarizes QA findings for the reviewer. It is advisory only, in line with the human-confirmed principle.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Existing in-house validation engine and workflow_engine**: no new dependency. This is the preferred option.
- **GoRules ZEN Engine** (https://github.com/gorules/zen): MIT, Rust core, `pip install zen-engine`. It evaluates JSON decision tables, which suit configurable approval routing and thresholds. Optional.
- **venmo/business-rules** (https://github.com/venmo/business-rules): MIT, a pure-Python rules DSL.
- **AACE RP 17R-97 / 18R-97** (https://library.aacei.org/pgd01/pgd01.shtml): estimate classes and the estimate input checklist. These can inform "estimate maturity" rules. The documents are paid for non-members, so the rules must be our own implementation, not copied text.
- **MCP**: I could not verify any MCP server dedicated to estimate review or approval. The practical route is to expose review and QA tools through the platform's own `erp_chat` tools or its own MCP surface.

## Priority: 4/5 — the parts already exist; connecting them into a validation-gated approval flow is a Medium job with high bid-protection value for small firms

## Sources
- https://github.com/gorules/zen
- https://pypi.org/project/zen-engine
- https://docs.gorules.io/reference/overview
- https://pypi.python.org/pypi/business-rules/1.0.1
- https://library.aacei.org/pgd01/pgd01.shtml
- https://www.autodesk.com/products/proest/overview
- https://marketplace.autodesk.com/apps/90b2b182-5db0-49e5-b405-9c572a6762ba
- https://www.g2.com/products/proest/features
