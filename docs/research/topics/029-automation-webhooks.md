# 029. Webhooks and automation platforms (n8n, Zapier, Make, Activepieces)

## What it does
Exposes ERP events (BOQ approved, RFI opened, change order priced, invoice due, tender bid received) to no-code automation platforms and lets those platforms push data back in (create a contact, RFI or document from a form or an email). For a small firm this replaces custom integration work: one ERP connector plus a platform's thousands of existing apps (accounting, CRM, Google Sheets, e-mail, e-signature) covers most "glue" needs without code.

## Already in the codebase (with file paths)
- Outgoing webhooks with CRUD, test send and delivery log: `backend/app/modules/integrations/models.py` (`WebhookEndpoint`, `WebhookDelivery`), `service.py` (`WebhookService.dispatch_event`), `router.py` (`/webhooks/`, deliveries, test).
- Wildcard event-bus forwarder that sends every event to matching hooks with an envelope (`event`, `data`, `event_id`, `timestamp`, `source_module`): `backend/app/core/event_handlers.py` (`_dispatch_to_webhooks`).
- HMAC-SHA256 `X-Webhook-Signature` over the body, SSRF guard before each send: `backend/app/core/url_safety.py`.
- API keys for programmatic access (inbound calls from automation tools): `backend/app/modules/users/models.py` (`APIKey`).

**Gaps:** delivery runs inline in the event handler and retries only once on 5xx (no queue, backoff or dead-letter, no automatic disable); the signature carries no timestamp or id, so it gives no replay protection and does not follow the Standard Webhooks headers; there is no REST-hook subscribe/unsubscribe API shaped for Zapier/Activepieces/Make, and no endpoint that publishes the event catalog or sample payloads; no published n8n node, Zapier app, Make app or Activepieces piece; dispatch loads all active hooks and filters them in Python.

## Who it helps and how much
- Owner/estimator at a 2-20 person firm: high value. They can "send approved estimate to accounting", "post new RFI to the team chat" or "log bid to a sheet" without a developer.
- Self-hosters: n8n or Activepieces running next to the ERP on one VPS keeps data local.
- Project impact: every new connector request ("does it integrate with X?") can be answered as "yes, through n8n/Zapier", which sharply cuts the long tail of custom connectors.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium**, mostly in `integrations`:
1. Harden delivery (S): send the Standard Webhooks headers (`webhook-id`, `webhook-timestamp`, `webhook-signature`) alongside the legacy header; queue deliveries (Celery, with an in-process fallback), retry with exponential backoff, auto-disable after N failures, add a "redeliver" endpoint.
2. Automation API (S-M): `POST/DELETE /api/v1/integrations/hooks/subscribe` (REST-hook pattern: target URL in, hook id out); `GET /events/catalog` listing event names, an i18n label and a sample payload per event, built from module manifests; polling fallback `GET /events/recent?type=&since=` for Zapier polling triggers and Make "Watch" modules.
3. Connectors (M, separate repos/packages): n8n community node `n8n-nodes-openconstructionerp` (declarative actions plus a programmatic trigger), an Activepieces piece (MIT, can be upstreamed), and later a Zapier CLI app and a Make custom app. Each one is thin: API-key auth, the trigger built on the subscribe endpoint, actions built on the existing REST routes.
4. Validation rule: reject subscriptions to unknown event names, and check payloads against the catalog schema.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- Standard Webhooks spec and `standardwebhooks` libraries (Python/JS), https://www.standardwebhooks.com/ (open spec, MIT libraries).
- n8n community nodes (declarative style, `n8n-community-node-package` keyword), https://docs.n8n.io/integrations/creating-nodes/build/declarative-style-node/. n8n itself uses the Sustainable Use License (fair-code, free to self-host internally, restricted for resale/embedding).
- n8n MCP Server Trigger node: exposes n8n workflows as MCP tools, so ERP automations can also be reached by AI agents (https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/).
- Activepieces pieces framework (TypeScript; webhook triggers use `context.webhookUrl` in onEnable/onDisable), https://www.activepieces.com/docs/build-pieces/piece-reference/triggers/webhook-trigger. Community core is MIT, and pieces are also exposed as MCP servers.
- Zapier Platform CLI REST-hook triggers (`performSubscribe`/`performUnsubscribe`), https://docs.zapier.com/platform/build/cli-hook-trigger. Building an app is free; end users pay per task. Zapier MCP (https://zapier.com/mcp) bills tool calls against the task quota.
- Make custom apps instant triggers (webhook-linked), https://developers.make.com/custom-apps-documentation/app-components/modules/instant-trigger. Free to build; end users pay for operations.
- I could not verify an existing first-party connector for OpenConstructionERP on any of these platforms; none appears to exist.

## Priority: 4/5 — the base exists; a small amount of hardening plus one n8n/Activepieces connector unlocks thousands of integrations for small firms
## Sources
- https://docs.n8n.io/integrations/creating-nodes/build/declarative-style-node/
- https://docs.n8n.io/connect/create-nodes/plan-your-node/choose-a-node-building-style
- https://github.com/n8n-io/n8n/blob/master/LICENSE.md
- https://docs.zapier.com/platform/build/cli-hook-trigger
- https://github.com/zapier/zapier-platform/blob/main/example-apps/rest-hooks/triggers/recipe.js
- https://developers.make.com/custom-apps-documentation/app-components/modules/instant-trigger
- https://developers.make.com/custom-apps-documentation/best-practices/instant-triggers-scheduled
- https://www.activepieces.com/docs/build-pieces/piece-reference/triggers/webhook-trigger
- https://github.com/activepieces/activepieces
- https://www.standardwebhooks.com/
- https://zapier.com/mcp
