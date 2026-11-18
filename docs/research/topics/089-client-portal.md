# 089. Client/Owner Portal (approvals, progress photos, invoices, selections)

## What it does
A restricted, branded view of a project for the paying client: approve or reject change orders and selections with a timestamped signature, see curated progress photos and a progress summary, view and pay invoices, and choose finishes from Good/Better/Best options against allowances. Residential tools such as Buildertrend sell this as a core feature (portal for selections, change-order approval, photos and progress), and reviews point to timestamped approval logs as protection when an owner later disputes a choice.

## Already in the codebase (with file paths)
- **Approvals exist, but only for internal users:** `backend/app/modules/changeorders/router.py` has `/{id}/approve/` with `approved_by`/`approved_at` and rejection fields (`models.py`). It is gated by `changeorders.approve` = `Role.MANAGER` (`changeorders/permissions.py`).
- **Roles:** `backend/app/core/permissions.py` has only ADMIN/MANAGER/EDITOR/VIEWER. There is no external CLIENT or guest role and no scoping to a single project.
- **Per-entity visibility:** `backend/app/modules/teams/models.py` `EntityVisibility` grants an entity to a team. A portal could reuse it ("visible to client").
- **Photos:** `backend/app/modules/documents/models.py` `ProjectPhoto` stores caption, GPS, tags, `taken_at` and category. There is no flag for "shared with client".
- **Invoices:** `backend/app/modules/finance/models.py` `Invoice` (with `invoice_direction`, retention, due date), `InvoiceLineItem` and `Payment`. There is no online payment or pay-link integration (no Stripe references in the code).
- **Signed URLs:** `backend/app/core/storage.py` `url_for(key, expires_in=...)` can give out time-limited file links.
- **Selections/allowances:** there is no module for these. The grep of `models.py` files turned up no selection or allowance entity.
- **Frontend:** `frontend/src/features` has no portal feature.

## Who it helps and how much
It matters most for small residential builders, remodelers and design-build firms, where the homeowner is the client and asks for updates and decisions every day. It cuts down on update emails, and the approval record shortens disputes. When invoices have a pay link, payment usually arrives sooner. It helps commercial GCs less, since they usually go through formal pay applications. Overall value is **High** for the small business segment, because it is a key reason contractors pick Buildertrend-class tools.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium-Large.** New module `backend/app/modules/client_portal/`, with `manifest.py` depending on `oe_projects`, `oe_changeorders`, `oe_finance` and `oe_documents`.
- **Auth:** a `PortalAccess` model (project_id, contact_id, hashed token, expiry, scopes). Clients get a magic-link login that issues a JWT with role `client`, tied to one project. All portal routes go under `/api/v1/client_portal/` with their own dependency, so internal RBAC stays untouched.
- **Sharing:** set a `shared_with_client` flag through `EntityVisibility` or a metadata flag on photos, documents, change orders and invoices. Files go out through `storage.url_for`.
- **Approvals:** the portal calls the change-order service with a `ClientApproval` record (name, IP, timestamp, optional signature image). An event `client_portal.approval.recorded` feeds notifications and the audit log.
- **Selections:** new `Selection`/`SelectionOption` models linked to BOQ positions and allowances. When a choice is approved, the system can propose a change order. Validation rule: an option that goes over the allowance must create a pending change order.
- **Payments:** optional `stripe` integration in `integrations/` that creates Payment Links or Stripe Invoices and reconciles them into `Payment` through a webhook.
- **Frontend:** a separate light-weight route bundle `frontend/src/features/client-portal`, with all strings through i18n.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Stripe Invoicing / Payment Links / ACH:** ACH costs 0.8% capped at $5. Invoicing adds a per-paid-invoice fee (0.4–0.5% shown on Stripe's regional invoicing pricing pages; confirm for your country). https://stripe.com/invoicing/pricing, https://stripe.com/payments/us-bank-payments
- **Stripe MCP server (official, public preview):** remote at mcp.stripe.com or npm `@stripe/mcp`. It lets `erp_chat` or agents create invoices and prices. https://docs.stripe.com/mcp
- **Documenso:** self-hostable e-signature with an API, AGPL-3.0 Community Edition (same license as this project), useful for formal signatures on change orders and contracts. https://docs.documenso.com/users/licenses/community-edition
- **CompanyCam API + webhooks:** for firms already capturing site photos there. Its docs say the current API is legacy and will be deprecated in early 2027, so it is risky to build on. https://docs.companycam.com/
- **Python stdlib `secrets` + existing JWT stack** for magic-link tokens, with no new dependency.
- **MCP:** I could not verify a dedicated "client portal" MCP server. Only the Stripe MCP fits here.

## Priority: 4/5 — High client-facing value for small residential builders, and most data models exist. The main work is a scoped external auth layer plus a new selections model.

## Sources
- https://buildertrend.com/house-building-software/
- https://buildertrend.com/frequently-asked-questions/
- https://connecteam.com/reviews/buildertrend/
- https://stripe.com/invoicing/pricing
- https://stripe.com/payments/us-bank-payments
- https://docs.stripe.com/mcp
- https://docs.documenso.com/users/licenses/community-edition
- https://docs.companycam.com/
