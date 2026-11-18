# 023. Subcontractor Portal and Bid Invitations (ITB Emails, Bid Submission Links)

## What it does

The estimator picks subcontractors from the contacts directory, attaches a bid package (scope, BOQ extract, drawings, due date) and sends an Invitation to Bid (ITB) by email. Each invitee gets a unique link that expires. Without creating an account, they can open the package, download the files, mark "will bid / won't bid", ask questions, and enter their unit prices against the BOQ lines or upload a PDF quote. Their answers go straight into the existing bid comparison and award flow. Commercial tools (BuildingConnected, Procore Bidding, ERPNext RFQ portal) treat this as the basic version of bid management.

## Already in the codebase (with file paths)

- `backend/app/modules/tendering/models.py`: `TenderPackage` and `TenderBid`. Bids store `contact_email`.
- `backend/app/modules/tendering/router.py`: package and bid CRUD, a comparison endpoint, `apply-winner` and a PDF export.
- `backend/app/modules/rfq_bidding/models.py`: `RFQ` with an `issued_to_contacts` JSON list, and `RFQBid` with scores and an award flag.
- `backend/app/modules/rfq_bidding/router.py`: `POST /bids/` needs an authenticated internal user with `rfq.create`. A subcontractor has no way to submit a bid themselves.
- `backend/app/core/email/` (smtp, console, memory and noop backends, plus `templates.py`): an email transport with templates for meetings, tasks and password reset. There is no ITB template.
- `backend/app/modules/contacts/models.py`: has `insurance` and `prequalification_status` fields, which are useful for choosing who to invite.

**Gap:** nothing sends invitations, there are no tokenized public links, no invitation tracking (sent, opened, declined, submitted), no reminders, no Q&A or addenda, and no public form for entering line-item prices. Today every bid has to be typed in by staff.

## Who it helps and how much

- **Small GCs and estimators:** High value. Retyping emailed quotes and chasing subs by phone takes up much of each bid cycle. Self-service submission cuts out the double entry and fills the comparison table directly.
- **Subcontractors:** They do not need an account or a licence. This matters a lot, because asking small trade firms to sign up for yet another portal makes them less likely to respond.
- **Owners or clients:** They get an audit trail of who was invited and when, which helps with fair-tender requirements.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)

**Medium.** Mainly `tendering` and `rfq_bidding`, plus `contacts`, `notifications`, `core/email` and a new public frontend route.

- New model `oe_tendering_invitation` (package_id, contact_id, email, status, token_hash, sent_at, opened_at, responded_at, expires_at), with an Alembic migration.
- `service.send_invitations()` signs a token (stdlib `hmac`/`secrets`, or itsdangerous) and keeps only its hash. It renders a new `template_bid_invitation` and sends it through `get_email_service()`. It publishes the event `tendering.invitation.sent`.
- New public router (`/api/v1/tendering/portal/{token}`) for GET package, POST intent, POST bid lines and file upload. It has no JWT; the token sets the scope, and the router is rate-limited. Submitting creates a `TenderBid`, sets the source to `portal`, and runs the `boq_quality` validation rules (missing prices, zero rates, outlier unit rates) before the estimator reviews it.
- Reminder job through the existing scheduler/Celery hook (for example 48 hours before the due date). An `.ics` attachment adds the due date to the sub's calendar.
- Frontend: an "Invite bidders" dialog in `features/tendering` and a lightweight, fully i18n `/portal/bid/:token` page.
- Optional later: an adapter in `integrations` that syncs with BuildingConnected for firms that already use it.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)

- **itsdangerous `URLSafeTimedSerializer`** (BSD-3) for signed links that expire: https://itsdangerous.palletsprojects.com/url_safe/. Python's built-in `secrets`/`hmac` would also work, with no extra dependency.
- **Existing `app.core.email` SMTP backend**: no new dependency.
- **icalendar** (BSD-2) for due-date `.ics` files: https://github.com/collective/icalendar
- **BuildingConnected API (Autodesk Platform Services)**: has invite, bid and bid-package endpoints, but needs a paid BuildingConnected Pro subscription. Good as an optional connector, not the core feature: https://aps.autodesk.com/en/docs/buildingconnected/v2/developers_guide
- **Reference UX: ERPNext RFQ supplier portal** (GPL-3, open source). Suppliers reply through the portal to create a draft quotation. It requires a login by default: https://docs.frappe.io/erpnext/user/manual/en/request-for-quotation
- **Reference UX: Procore Bidding "Invite Bidders"** (proprietary): https://v2.support.procore.com/product-manuals/bidding-project/tutorials/invite-bidders
- **MCP:** a community Procore MCP server lists bid-package and bid tools (https://glama.ai/mcp/servers/TylerIlunga/procore-mcp-server/tools/create_bid_package). I only saw its listing page; I did not check maturity or licence. I found no official MCP server for BuildingConnected or ConstructConnect.

## Priority: 5/5 — the bid models are already built but no one outside the company can reach them; a portal with tokenized links is medium effort and saves the most data entry in each tender cycle

## Sources

- https://aps.autodesk.com/en/docs/buildingconnected/v2/developers_guide
- https://aps.autodesk.com/en/docs/buildingconnected/v2/reference/http/buildingconnected-invites-GET
- https://v2.support.procore.com/product-manuals/bidding-project/tutorials/invite-bidders
- https://docs.frappe.io/erpnext/user/manual/en/request-for-quotation
- https://docs.frappe.io/erpnext/how-to-create-a-supplier-quotation-through-the-supplier-portal
- https://itsdangerous.palletsprojects.com/url_safe/
- https://github.com/collective/icalendar
- https://glama.ai/mcp/servers/TylerIlunga/procore-mcp-server/tools/create_bid_package
- https://downtobid.com/blog/how-much-is-building-connected
