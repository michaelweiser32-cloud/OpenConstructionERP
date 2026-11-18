# 097. Procore Integration (API, Marketplace App, Data Sync)

## What it does
Procore is a widely used cloud construction-management platform, mostly used by mid-size and large GCs. Its integration surface is:
- **REST API**: `api.procore.com/rest/v1.0|v1.1|v2.0/...`, plus a sandbox environment. Every call needs a `Procore-Company-Id` header. It covers projects, budgets and budget line items, cost codes/WBS, change orders, commitments, RFIs, submittals, daily logs, documents and more.
- **OAuth 2.0**: Authorization Code for user-facing apps, or client credentials through a Developer Managed Service Account (DMSA) for unattended sync.
- **Webhooks**: Procore recommends them over polling.
- **Rate limits**: an hourly window plus a 10-second spike window. Clients must throttle on the response headers. Third-party docs often quote 3,600 requests per hour as the default, but Procore says the headers are authoritative.
- **App Marketplace**: listing is currently free for Technology Partners. It requires a partner agreement, a review questionnaire, a demo video and at least one beta customer.

For an estimating ERP, the useful flows are: push the BOQ to a Procore Budget as line items mapped to cost code and cost type; pull change orders and commitments back for cost tracking; sync the project list; and, optionally, mirror RFIs and submittals.

## Already in the codebase (with file paths)
- `backend/app/core/marketplace.py` (about line 836) has a **catalog entry only**: `integration-procore`, "Procore Connector", described as "bi-directional sync", version 1.0.0, `requires=["oe_projects","oe_boq"]`. No module ships behind it. No `procore` directory, client, OAuth flow or mapping code exists anywhere.
- `backend/app/modules/integrations/` (`models.py`: `IntegrationConfig`, `WebhookEndpoint`, `WebhookDelivery`) is built for outbound chat notifications (Slack, Teams, Telegram and others). Its per-user `config` JSON and webhook tables can be reused, but there is no OAuth token storage or refresh.
- Procore also appears in marketing text: `frontend/src/features/about/AboutPage.tsx` and `frontend/src/app/i18n-fallbacks.ts`.
- **Gap:** the marketplace advertises a connector that does not exist. That is a credibility risk; it should be labelled "planned" or built.

## Who it helps and how much
- **Estimators and subcontractors who bid to Procore-using GCs.** Handing over an estimate as a Procore budget, or a cost-coded CSV, saves re-keying. Medium value.
- **Small GCs that already pay for Procore.** They could use OpenConstructionERP as the estimating front end, a gap Procore's own estimating product fills at extra cost. Medium-high value for this niche.
- **Most small firms.** Third-party estimates put Procore's minimum annual contract at roughly $4.5k to $15k, priced by annual construction volume, so many small contractors do not use it. Low value for them. A CSV export in Procore's budget-import format (cost code and cost type columns, 500 lines per import) covers much of the benefit at a fraction of the effort.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium** for a one-way MVP. **Large** for true bi-directional sync and a Marketplace listing.
- New module `backend/app/modules/procore/` with `manifest.py` (`depends=["oe_projects","oe_boq","oe_integrations"]`), `models.py` (OAuth tokens encrypted at rest, plus a mapping table for local ID, Procore ID and entity type), `client.py` (httpx with header-based throttling and exponential backoff on 429), `service.py`, `router.py` (OAuth callback, a webhook receiver, `/push-budget`, `/pull-change-orders`) and `validators.py`. Validation rules would check that every BOQ position has a cost code and cost type mapped before a push.
- Long syncs run as background tasks. Inbound webhooks publish events on the core event bus, for example `procore.change_order.updated`, which the `changeorders` module consumes.
- Phase 1: a CSV export in Procore's budget-import format. No partner agreement is needed; this is Small effort.
- Phase 2: OAuth plus pushing budget line items. Phase 3: webhooks and pulling change orders and commitments. Phase 4: the Marketplace listing (agreements, beta customer, review).
- Each company must create its own developer-portal app, or the project must operate one shared OAuth app. A shared app is awkward for self-hosted AGPL deployments because the client secret cannot be distributed.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Procore REST API and developer portal**: https://developers.procore.com. Developer accounts and sandbox are free. Production access needs the customer's Procore subscription. Note: this host was blocked from this session's network, so the portal was not checked directly; the details here come from Procore's GitHub Pages documentation.
- **Procore documentation**, mirrored at https://procore.github.io/documentation/ (rate limiting, Marketplace requirements, verification).
- **procore-mcp-server** (community, not official), MIT, TypeScript: https://github.com/TylerIlunga/procore-mcp-server. It offers 7 discovery tools plus a generic API-call tool, and supports OAuth Authorization Code or DMSA client credentials. It is useful as a reference or as an optional `erp_chat` tool bridge. It has about 20 stars and no releases. I found **no official Procore MCP server**.
- **Commercial unified APIs and MCP**: Agave (https://docs.agaveapi.com), CData, Pipedream (https://mcp.pipedream.com/app/procore), Truto. All are paid or proprietary, so they are not suitable as core dependencies.
- **httpx** (BSD-3) and **authlib** (BSD-3) for OAuth2. Both are already common in FastAPI stacks.

## Priority: 2/5 — Advertised but missing. Procore is a high-cost tool few small firms use, so ship the CSV budget export first and build OAuth sync only on demand.

## Sources
- https://procore.github.io/documentation/rate-limiting
- https://procore.github.io/documentation/marketplace-requirements
- https://procore.github.io/documentation/listing-your-app
- https://procore.github.io/documentation/verification-and-production-access
- https://procore.github.io/documentation/integration-health
- https://support.procore.com/products/online/user-guide/project-level/budget/tutorials/import-a-budget
- https://support.procore.com/faq/common-questions-apps-and-marketplace
- https://sync-docs.agaveapi.com/docs/procore-and-foundation/budget-line-items
- https://github.com/TylerIlunga/procore-mcp-server
- https://mcp.pipedream.com/app/procore
- https://www.getonecrew.com/post/procore-pricing
- https://www.costbench.com/software/construction-management/procore/
