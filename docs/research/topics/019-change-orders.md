# 019. Change order workflow with cost and schedule impact, owner approval, CO log

## What it does
A change order (CO) workflow records a scope change, prices it, states its time impact and gets the owner to approve it. It then carries the result into the budget, the schedule and billing. The industry reference is the AIA G701 form. Each CO lists the original contract sum, the net effect of earlier COs, the contract sum before this CO, this CO's change and the new contract sum. It does the same for contract time and the substantial completion date. A G701 becomes binding once owner, contractor and architect have all signed it. Larger platforms such as Procore add a "two-tier" flow: a change event leads to a potential change order (PCO), and an approved PCO becomes a prime contract change order. The CO log is the running register of all COs, with their status and totals.

## Already in the codebase (with file paths)
The core flow is already solid:
- `backend/app/modules/changeorders/models.py` has two tables.
  - `ChangeOrder` holds `cost_impact`, `schedule_impact_days`, and the variation fields `contractor_amount`, `engineer_amount`, `approved_amount`, `time_impact_days` and `approved_time_days`. It also records who submitted, approved or rejected the CO, and when.
  - `ChangeOrderItem` holds per-line deltas: original and new quantity, original and new rate, and `cost_delta`.
- `backend/app/modules/changeorders/service.py` implements the status machine draft -> submitted -> approved/rejected. A submitter cannot approve their own CO. Approval is idempotent, and on approval `cost_impact` is added to `project.budget_estimate` and a `changeorder.approved` event is published.
- `router.py` has the CRUD, item, submit, approve and reject endpoints, plus `/summary/`.
- `frontend/src/features/changeorders/ChangeOrdersPage.tsx` is a single page of about 1,300 lines with the list and editor.
- COs can be created from an RFI (`backend/app/modules/rfi/router.py`) or an NCR (`backend/app/modules/ncr/router.py`). The project dashboard reads them (`backend/app/modules/projects/router.py`). Backup includes them (`backend/app/modules/backup/router.py`).

**Gaps:**
1. No module subscribes to `changeorder.approved`, so the approved time is never applied to `schedule` (project `end_date` or activities). The `full_evm` baseline and `finance` billing (SOV/pay application lines) are not updated either.
2. There is no owner-facing approval. Approval needs an internal user, and there is no signed CO document: no G701-style PDF with the running contract sum and contract time.
3. There is no exportable CO log (PDF/Excel) showing original contract, approved COs, pending exposure and revised contract.
4. There is no PCO/change-event tier, and no OH&P markup on COs.
5. There are no CO-specific validation rules, for example "approved_amount differs from the sum of items" or "schedule impact missing".

## Who it helps and how much
- **Small general contractors and specialty subcontractors (High):** unbilled or undocumented change work is a classic source of margin leakage. Getting the owner's signature on the price and the days before doing the work is the main protection.
- **Estimators (Medium):** they can reuse BOQ rates to price COs, which the item deltas already support.
- **Owners and PMs (Medium):** the CO log with pending exposure is the first thing they ask for in progress meetings.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium overall.** The core already exists, so the work is wiring and outputs:
- **S:** handlers in `schedule/events.py` and `finance/events.py` for `changeorder.approved`. One shifts the project or contract completion date by `approved_time_days`, the other adds a SOV line. Add `approved_time_days` and `contract_id` to the event payload.
- **S:** CO PDF and CO log export. Use `reportlab`, which is already a backend dependency, in `changeorders/service.py`, and add `GET /{id}/pdf` and `GET /log/export`. Compute the running contract sum (original + previous approved + this CO) on the server.
- **M:** owner approval link. Create a signed, expiring token (the JWT infrastructure already exists) for a public approve/reject page. It records the approver's name, IP and timestamp in `metadata`, and the `notifications` and email integrations send it. An optional e-signature step can go through a separate plugin module, e.g. a Documenso bridge, so core stays lightweight.
- **S:** validation rules `changeorder.amount_matches_items` and `changeorder.time_impact_declared`, using the core validation engine.
- **M (later):** a PCO tier as a new `pending_owner` status plus a `parent_id` grouping.
- **AI hook:** `erp_chat/tools.py` tools to "draft CO from RFI" and "summarize CO log". The AI drafts, and a human submits.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **ReportLab** (already in `pyproject.toml`; BSD) for the CO and log PDFs. **WeasyPrint** (BSD-3) is an HTML/CSS-to-PDF alternative: https://github.com/Kozea/WeasyPrint
- **Documenso**, a self-hostable e-signature platform. The Community Edition is AGPL-3.0, which matches this project's license, and a commercial Enterprise license exists. It has an API. https://docs.documenso.com/users/licenses/community-edition
- **AIA G701** defines the field structure. The form itself is copyrighted and sold by AIA, so copy the structure, not the form text. https://help.aiacontracts.com/hc/en-us/articles/1500009384382
- **Procore** documents the two-tier PCO/CO model. It is a reference for import/sync, and access needs a Procore developer account. https://support.procore.com/products/online/user-guide/project-level/change-events/tutorials/create-a-prime-potential-change-order-from-a-change-event
- **MCP:** there is no official Procore MCP server. The community `TylerIlunga/procore-mcp-server` (listed as MIT) is unverified and only useful for users who also run Procore. https://github.com/TylerIlunga/procore-mcp-server
- No dedicated, verified MCP server for change orders exists. Exposing this module's own endpoints through `erp_chat` tools is the realistic route.

## Priority: 4/5 — the core exists, and closing the gaps (schedule/finance writeback, a signed owner approval, a CO log export) is cheap, high-value work that directly protects a small contractor's margin.

## Sources
- https://help.aiacontracts.com/hc/en-us/articles/1500009384382
- https://help.aiacontracts.com/hc/en-us/articles/1500009322061-Instructions-G701-2017-Change-Order
- https://learn.aiacontracts.com/articles/6378493-the-fundamentals-of-change-orders-in-construction/
- https://support.procore.com/products/online/user-guide/project-level/change-events/tutorials/create-a-prime-potential-change-order-from-a-change-event
- https://support.procore.com/products/online/user-guide/project-level/change-events/tutorials/create-a-prime-contract-change-order-from-a-change-event
- https://docs.documenso.com/users/licenses/community-edition
- https://docs.documenso.com/developers/self-hosting
- https://github.com/Kozea/WeasyPrint
- https://github.com/TylerIlunga/procore-mcp-server
