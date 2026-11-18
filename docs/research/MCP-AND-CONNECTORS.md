# MCP Servers and Connectors: How They Plug Into OpenConstructionERP

**Status:** research only. This document describes no implemented features.
**Companion to:** [FEATURE-RESEARCH-100.md](FEATURE-RESEARCH-100.md). Per-topic evidence and sources are in [`topics/`](topics/).
All links point to public documentation or repositories. "Official" means published by the vendor itself. Where no official API or MCP server exists, this document says so.

---

## 1. What already exists (the plumbing to reuse)

| Building block | Location | How connectors use it |
|---|---|---|
| Module system | `app/core/module_loader.py`, `MODULES.md` | Each connector is a module with `manifest.py` (`category="integration"`, `depends=[...]`, `auto_install=False`), so users enable it from `/modules` |
| Event bus | `app/core/events.py` (`EventBus.on/subscribe/publish`, names like `{module}.{entity}.{action}`) | Outbound sync subscribes to domain events, e.g. `finance.invoice.approved` → push to QuickBooks/Xero. Inbound sync publishes events, e.g. `integrations.email.received` |
| Hook registry | `app/core/hooks.py` (filters + actions) | Lets modules extend shared lists, e.g. a `mcp.tools` filter so each module contributes MCP tools |
| Integration config | `modules/integrations/models.py` (`oe_integrations_config`, per user/project, `integration_type`) | Stores connector settings; extend it for OAuth tokens and sync cursors |
| Outgoing webhooks + delivery log | `oe_integrations_webhook`, `oe_integrations_delivery` (HMAC-signed) | Base layer for the n8n/Zapier/Make/Activepieces bridge |
| Existing send-only connectors | `modules/integrations/{slack,teams,telegram,whatsapp,discord,email_service}.py` | Reuse them, adding inbound webhooks and event-bus wiring ([048](topics/048-whatsapp-telegram.md), [049](topics/049-slack-teams.md)) |
| Secret encryption | `app/core/crypto.py` (`encrypt_secret`/`decrypt_secret`) | Encrypts OAuth refresh tokens, API keys and MCP server tokens at rest |
| SSRF guard | `app/core/url_safety.py` (`resolve_and_validate_external_url`) | Validate every outbound connector and MCP URL before connecting |
| Audit + RBAC | `app/core/audit.py`, `app/core/permissions.py` | Log every external write and MCP tool call; gate connector admin behind permissions |
| AI tool registry | `modules/erp_chat/tools.py` (`TOOL_DEFINITIONS`, `TOOL_HANDLER_MAP`) | The ready-made tool set an ERP MCP server can expose ([071](topics/071-erp-as-mcp-server.md)) |
| Storage | `app/core/storage.py` (local / S3-compatible) | Target for files imported from cloud drives and email attachments |

**Gaps found across reports:**
- There is no shared OAuth 2.0 token store with refresh handling.
- There is no generic sync-cursor model (delta tokens, webhooks, idempotency keys).
- There is no inbound-webhook receiver framework.
- There is no MCP code at all, neither a server nor a client.

Building these once, as a small core layer, makes every connector after the first much cheaper.

---

## 2. Recommended architecture

```
               ┌──────────────────────── OpenConstructionERP ─────────────────────────┐
External AI    │  mcp_server module  ──wraps──>  erp_chat TOOL_DEFINITIONS + hooks     │
clients  ────► │  (/mcp, Streamable HTTP, API key → OAuth 2.1, RBAC, audit, confirm)   │
(Claude etc.)  │                                                                       │
               │  connector_core (in integrations):                                    │
               │   OAuthToken(encrypted) · SyncCursor · InboundWebhook · RetryQueue     │
               │        ▲                         │                                    │
               │        │ events                  ▼ events                             │
               │  accounting_qbo / xero_connector / cloud_drive_* / email_inbox /     │
               │  esign / payments_gateway / ...   (one module each, manifest-based)  │
               │                                                                       │
               │  erp_chat MCP client ──► allow-listed external MCP servers            │
               │  (namespaced tools, hash pinning, human approval for writes)          │
               └───────────────────────────────────────────────────────────────────────┘
```

### 2.1 `connector_core` (extension of `oe_integrations`)
Proposed models:
- `OAuthConnection(tenant/user, provider, scopes, encrypted_refresh_token, expires_at)`
- `SyncCursor(connection, resource, cursor/delta_token, last_synced_at)`
- `ExternalLink(entity_type, entity_id, provider, external_id, etag)`, which maps ERP rows to remote IDs, enables idempotent upserts and avoids duplicates
- `InboundEvent(provider, signature_verified, payload, processed_at)`

Proposed services:
- an OAuth authorize/callback router per provider
- a signature verifier per provider
- retries with backoff (Celery, or the in-process fallback)
- a validation hook that runs before data from an external sync is stored. This keeps the project rule that every import passes validation.

### 2.2 One module per connector
Example manifest pattern:

```python
manifest = ModuleManifest(
    name="oe_accounting_qbo",
    display_name="QuickBooks Online",
    category="integration",
    depends=["oe_integrations", "oe_finance", "oe_contacts", "oe_costmodel"],
    auto_install=False,
)
```

Each connector module then provides:
- `service.py` with the provider SDK calls
- `events.py` with subscriptions such as `finance.invoice.approved → push_invoice`
- `router.py` with OAuth, a manual sync trigger and a mapping UI API
- `validators.py`, e.g. "every synced bill maps to a cost code"
- frontend settings under `frontend/src/modules/<name>/`

### 2.3 MCP in both directions
- **Server, highest priority** ([071](topics/071-erp-as-mcp-server.md)): a new `mcp_server` module built on the official [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk) or [FastMCP](https://github.com/jlowin/fastmcp).
  - It registers curated `erp_chat` tools, not an auto-mirror of the whole OpenAPI surface, plus resources for projects, BOQs and validation reports.
  - It is mounted at `/mcp` over Streamable HTTP.
  - Auth starts with API keys mapped to users and RBAC, then moves to [OAuth 2.1 per the MCP spec](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization).
  - Write tools return proposals or require `confirm=true`, matching the "AI proposes, human confirms" rule.
- **Client, second** ([080](topics/080-mcp-client-architecture.md)): `McpServer` records per tenant hold the URL, encrypted token, allowed tools and the tools that need approval.
  - Tools are namespaced as `mcp__<server>__<tool>`, and tool-definition hashes are pinned so a changed definition is disabled until it is re-reviewed.
  - Every connection goes through the SSRF guard, and MCP output is treated as untrusted data in the prompt.
  - Stdio servers are off by default.
  - See the [OWASP MCP security cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html).
- **Rule of thumb:** prefer a direct REST connector for anything that must be reliable, such as accounting sync or document sync. Use external MCP servers for ad-hoc assistant tasks (search, messaging, lookups), where a human reviews the result.

---

## 3. Connector catalogue

Priority comes from the topic report (1–5).
**Official SDK / API** is the recommended integration path.
**MCP** lists existing MCP servers, which are useful through the `erp_chat` MCP client or the user's own AI client. Many are young or in preview.

### 3.1 Accounting, finance and payments

| Connector | Priority | Proposed module & events | Official SDK / API | MCP server | Notes |
|---|---|---|---|---|---|
| QuickBooks Online ([031](topics/031-quickbooks.md)) | 5 | `oe_accounting_qbo`; push customers/invoices/bills on `finance.*.approved`; pull actuals by Class/Customer → `costmodel` | [python-quickbooks](https://github.com/ej2/python-quickbooks) (community), [QBO API](https://developer.intuit.com/app/developer/qbo/docs/workflows/manage-linked-transactions) | [intuit/quickbooks-online-mcp-server](https://github.com/intuit/quickbooks-online-mcp-server) (official) | Check the Intuit App Partner Program API metering ([overview](https://www.apideck.com/blog/quickbooks-api-pricing-and-the-intuit-app-partner-program)) |
| Xero ([032](topics/032-xero.md)) | 4 | `oe_xero_connector`; tracking categories ↔ projects/cost codes | [xero-python](https://github.com/XeroAPI/xero-python) (MIT) | [XeroAPI/xero-mcp-server](https://github.com/XeroAPI/xero-mcp-server) (official, MIT) | Strongest in AU/NZ/UK; see [pricing tiers](https://developer.xero.com/pricing) |
| Sage ([033](topics/033-sage.md)) | 3 | Shared `accounting_sync` adapter | REST only for [Sage Accounting](https://developer.sage.com/accounting/guides/concepts/overview) and [Intacct](https://developer.sage.com/intacct/docs/openapi/z-indexes/index-cre) | Intacct AI gateway (read-only) | Sage 50/100 Contractor/300 CRE need file exports |
| Stripe / Mollie payments ([034](topics/034-client-payments.md)) | 4 | `oe_payments_gateway`; payment links on invoices; webhook → `finance.payment.received` | Stripe API (ACH/SEPA) | [Stripe MCP](https://docs.stripe.com/mcp), [Mollie MCP](https://docs.mollie.com/docs/mollie-mcp-server) | Capped ACH/SEPA fees beat card fees on large invoices |
| E-invoicing XRechnung/ZUGFeRD/Peppol ([040](topics/040-currency-vat-einvoice.md)) | 5 | `oe_einvoice`; generate/parse on `finance.invoice.*`; KoSIT validation as a validation rule set | [python-drafthorse](https://github.com/pretix/python-drafthorse), [factur-x](https://github.com/akretion/factur-x), [KoSIT validator](https://github.com/itplr-kosit/validator) | none needed | Legally mandated in Germany |
| Invoice capture / AP ([035](topics/035-invoice-ocr-ap.md)) | 4 | `oe_ap_capture`; email/drive inbound → extract → PO match → human-confirmed cost coding | [invoice2data](https://github.com/invoice-x/invoice2data), [docling](https://github.com/docling-project/docling) | — | Pairs with e-invoice parsing |
| Bank feeds ([036](topics/036-bank-feeds.md)) | 3 | `oe_bank_feeds`; CAMT/MT940/OFX import first | [Plaid](https://plaid.com/docs/transactions/) (optional) | — | GoCardless Bank Account Data is reported closed to new signups ([source](https://actualbudget.org/docs/advanced/bank-sync/gocardless/)) |
| Payroll (Gusto/ADP/Finch/Merge) ([038](topics/038-payroll-connectors.md)) | 2 | Later, after per-worker timesheets ([039](topics/039-field-timesheets.md)) | [Gusto](https://docs.gusto.com/app-integrations/docs/syncing-time-tracking-data), [Finch](https://tryfinch.com/pricing), [Merge](https://docs.merge.dev/hris/) | — | Requires vendor partner approval |

### 3.2 Documents and drawings (one shared `cloud_drive` layer, four adapters)

| Connector | Priority | Proposed module & events | Official SDK / API | MCP server | Notes |
|---|---|---|---|---|---|
| OneDrive / SharePoint ([043](topics/043-onedrive-sharepoint.md)) | 4 | `oe_ms_graph`; delta query + change notifications → `documents`/`cde` revision | [msgraph-sdk-python](https://github.com/microsoftgraph/msgraph-sdk-python), [driveItem delta](https://learn.microsoft.com/graph/api/driveitem-delta) | [Softeria/ms-365-mcp-server](https://github.com/Softeria/ms-365-mcp-server) (community) | Graph auth can be shared with Outlook mail/calendar |
| Google Drive ([041](topics/041-google-drive.md)) | 4 | `cloud_drive_google`; Picker + `drive.file` scope (avoids restricted-scope verification) | [google-api-python-client](https://github.com/googleapis/google-api-python-client), [scopes guide](https://developers.google.com/workspace/drive/api/guides/api-specific-auth) | [Google Drive MCP](https://developers.google.com/workspace/drive/api/reference/mcp) (preview) | |
| Dropbox ([042](topics/042-dropbox.md)) | 4 | `cloud_drive_dropbox`; webhooks + cursor | [dropbox-sdk-python](https://github.com/dropbox/dropbox-sdk-python), [webhooks](https://www.dropbox.com/developers/reference/webhooks) | [Dropbox MCP](https://help.dropbox.com/integrations/connect-dropbox-mcp-server) | |
| Box ([044](topics/044-box.md)) | 3 | `cloud_drive_box`; V2 webhooks | [box-python-sdk-gen](https://github.com/box/box-python-sdk-gen) | [Box MCP](https://developer.box.com/guides/box-mcp) (official, remote) | |
| Bluebeam ([099](topics/099-bluebeam.md)) | 3 | Revu markup CSV/XML import into `markups` + `boq` first; Studio API later | [Markups list export](https://support.bluebeam.com/user-manual/menus/window/markups-list.html), [Studio API](https://support.bluebeam.com/developer/studio-session-guide.html) | Bluebeam's own MCP feature ([docs](https://support.bluebeam.com/revu/how-to/mcp-anything.html)) | Studio API sits behind paid tiers and vendor approval |
| Procore ([097](topics/097-procore.md)) | 2 | CSV budget export first; OAuth sync on demand | [Marketplace requirements](https://procore.github.io/documentation/marketplace-requirements), [rate limits](https://procore.github.io/documentation/rate-limiting) | community only | The current marketplace listing advertises a connector that does not exist |
| Autodesk Build / APS ([098](topics/098-autodesk-aps.md)) | 2 | `acc_connector` for files/RFIs/issues/Cost | [ACC API](https://aps.autodesk.com/en/docs/acc/v1/), [Cost integration](https://aps.autodesk.com/en/docs/acc/v1/tutorials/cost/integrate-with-external-system) | [aps-mcp-server-nodejs](https://github.com/autodesk-platform-services/aps-mcp-server-nodejs) (reported archived) | Models are already covered by DDC conversion; the value is ACC interop |

### 3.3 Communication, calendar and signature

| Connector | Priority | Proposed module & events | Official SDK / API | MCP server | Notes |
|---|---|---|---|---|---|
| Inbound email → RFI/correspondence ([046](topics/046-email-integration.md)) | 4 | `oe_email_inbox`; publishes `integrations.email.received` → `correspondence`/`rfi` with human triage | [imap_tools](https://github.com/ikvk/imap_tools), [Gmail push](https://developers.google.com/gmail/api/guides/push), [Graph notifications](https://learn.microsoft.com/graph/change-notifications-overview) | Gmail MCP (via Google Workspace, [075](topics/075-google-workspace-mcp.md)) | Start with IMAP (no OAuth review) |
| Slack / Teams ([049](topics/049-slack-teams.md)) | 4 | Wire existing connectors to the event bus; signed interactive buttons for approvals | [bolt-python](https://github.com/slackapi/bolt-python) | [Slack MCP](https://docs.slack.dev/ai/slack-mcp-server/) | Teams Office 365 connectors are being retired; move to Workflows ([notice](https://mc.merill.net/message/MC1181996)) |
| WhatsApp / Telegram field bots ([048](topics/048-whatsapp-telegram.md)) | 4 | `field_messaging`; inbound webhooks → photo/diary/punch drafts → confirm-before-save | [Telegram Bot API](https://core.telegram.org/bots/api), [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api) | — | WhatsApp uses [per-message pricing](https://developers.facebook.com/docs/whatsapp/pricing) |
| SMS ([047](topics/047-sms.md)) | 3 | Adapter in `integrations` + `notifications` | Twilio/Vonage over httpx; [apprise](https://github.com/caronc/apprise) | [twilio-labs/mcp](https://github.com/twilio-labs/mcp) | US [A2P 10DLC](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc) registration and opt-out compliance |
| Calendar ([050](topics/050-calendar.md)) | 4 | Fix the ICS feed first (small effort); then two-way Google/Graph/CalDAV sync | [icalendar](https://icalendar.readthedocs.io/en/stable/), [Graph events](https://learn.microsoft.com/en-us/graph/api/user-post-events), [caldav](https://github.com/python-caldav/caldav) | Google Calendar MCP (via Workspace) | The current feed uses weak prefix-only token auth |
| E-signature ([051](topics/051-e-signature.md)) | 4 | `oe_esign`; `changeorders.co.submitted` → envelope → webhook `esign.completed` → CO approved | Self-host [DocuSeal](https://github.com/docusealco/docuseal) / [Documenso](https://github.com/documenso/documenso); DocuSign API | [DocuSign MCP](https://developers.docusign.com/platform/mcp-server) | A self-hosted option fits the AGPL / single-database philosophy |
| Meeting transcripts ([057](topics/057-meetings.md)) | 4 | Pull into `meetings` | [Graph callTranscript](https://learn.microsoft.com/en-us/graph/api/calltranscript-get), [Zoom cloud recording](https://developers.zoom.us/docs/build/cloud-recording/) | — | |

### 3.4 Automation and public data

| Connector | Priority | Proposed module & events | Official SDK / API | MCP server | Notes |
|---|---|---|---|---|---|
| Webhooks + n8n / Activepieces / Zapier / Make ([029](topics/029-automation-webhooks.md)) | 4 | Harden `integrations` webhooks (Standard Webhooks headers, queued retries); add `/hooks/subscribe` + `/events/catalog` built from manifests | [n8n declarative node](https://docs.n8n.io/integrations/creating-nodes/build/declarative-style-node/), [Activepieces webhook trigger](https://www.activepieces.com/docs/build-pieces/piece-reference/triggers/webhook-trigger), [Zapier REST hooks](https://docs.zapier.com/platform/build/cli-hook-trigger) | (n8n/Activepieces can themselves expose MCP) | One integration surface reaches hundreds of apps without custom code |
| Weather ([083](topics/083-weather.md)) | 4 | `weather` service → `fieldreports` + weather-day log → `changeorders`/EOT evidence | [Open-Meteo](https://open-meteo.com/en/pricing) (incl. historical), [NWS API](https://www.weather.gov/documentation/services-web-api), [Bright Sky](https://brightsky.dev/) (DWD) | [mcp_weather_server](https://github.com/isdaniel/mcp_weather_server) | Check Open-Meteo's non-commercial terms for hosted SaaS use |
| Price indices ([024](topics/024-price-feeds.md), [004](topics/004-public-cost-data.md)) | 4 | `price_indices` → escalation in `costs`/`boq` (replaces LLM-guessed escalation) | [BLS API](https://www.bls.gov/developers/api_faqs.htm), [FRED](https://fred.stlouisfed.org/), [Destatis](https://www.destatis.de/EN/Service/OpenData/api-webservice.html), [DBnomics](https://docs.db.nomics.world/web-api/) | — | Free, defensible sources |
| Tender leads ([090](topics/090-bid-boards.md)) | 3 | `bid_board` → creates tendering/CRM opportunities | [SAM.gov Opportunities](https://open.gsa.gov/api/get-opportunities-public-api/), [TED API](https://docs.ted.europa.eu/api/latest/index.html) | — | Dodge/ConstructConnect are paid; BidNet has no public API |
| Vendor checks ([030](topics/030-vendor-database.md), [022](topics/022-sub-prequal.md)) | 4 | `contacts` enrichment + validation rules | [SAM Entity API](https://open.gsa.gov/api/entity-api/), [SAM Exclusions](https://open.gsa.gov/api/exclusions-api), [Companies House](https://developer.company-information.service.gov.uk/), EU VIES | — | Free official registries |
| Supplier catalogs ([027](topics/027-product-catalogs.md)) | 4 | `catalog` import of DATANORM / BMEcat / ETIM xChange | [datanorm parser](https://github.com/FahrJo/datanorm), [ETIM xChange](https://www.etim-international.com/classification/exchange-format/) | — | BIMobject/EC3 APIs are gated or paid; keep them as optional plugins |
| Permits ([084](topics/084-permit-data.md)) | 3 | Internal permit register first; US open data optional | [Socrata SODA](https://dev.socrata.com/docs/endpoints), [Accela](https://developer.accela.com/docs/construct-api-records.html) (agency-gated), [Shovels](https://shovels-v2.redoc.ly) (paid) | — | |
| Geocoding ([082](topics/082-maps-geocoding.md)) | 2 | Server-side geocode proxy/cache in a `geo` service | Nominatim ([usage policy](https://operations.osmfoundation.org/policies/nominatim/)), [Photon](https://github.com/komoot/photon) | — | A MapLibre + Nominatim map already exists |

---

## 4. MCP servers: fit for this ERP

| MCP server | Direction | Priority | Use in this ERP | Safety requirements |
|---|---|---|---|---|
| **OpenConstructionERP MCP server** ([071](topics/071-erp-as-mcp-server.md)) | ERP → external AI | **5** | Users' own Claude/ChatGPT/IDE agents can query projects, BOQs, costs and validation, and draft BOQ positions | RBAC per API key; write tools only as proposals or with `confirm=true`; audit; rate limits |
| MCP client in `erp_chat` ([080](topics/080-mcp-client-architecture.md)) | ERP ← external | 3 | Enables all the rows below inside the built-in assistant | Admin-only registry; allowlists; hash pinning; approval for writes; SSRF guard |
| Communication: [Slack MCP](https://docs.slack.dev/ai/mcp-server/), [Twilio MCP](https://github.com/twilio-labs/mcp), Gmail ([079](topics/079-communication-mcp.md)) | ERP ← external | 4 | Draft and send RFI follow-ups and sub reminders from chat | Human approval before any send |
| Accounting: [QBO MCP](https://github.com/intuit/quickbooks-online-mcp-server), [Xero MCP](https://github.com/XeroAPI/xero-mcp-server), [Stripe MCP](https://docs.stripe.com/mcp) ([078](topics/078-accounting-mcp.md)) | ERP ← external | 3 | Ad-hoc finance questions; the REST connectors remain the system of record | Read-only by default |
| Google Workspace: [official preview servers](https://developers.google.com/workspace/guides/configure-mcp-servers), [google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) (MIT) ([075](topics/075-google-workspace-mcp.md)) | ERP ← external | 3 | Find tender docs in Drive, schedule site meetings | Google-hosted servers are still in Developer Preview |
| Web search: [Tavily](https://github.com/tavily-ai/tavily-mcp), [Brave](https://github.com/brave/brave-search-mcp-server), Exa, Perplexity ([076](topics/076-web-search-mcp.md)) | ERP ← external | 3 | Datasheets and indicative prices, stored as evidence with the source URL | Web prices are unreliable; mark them as AI-suggested with a confidence score |
| Database: [Postgres MCP Pro](https://github.com/crystaldba/postgres-mcp) (restricted mode), [DBHub](https://github.com/bytebase/dbhub) (readonly) ([074](topics/074-database-mcp.md)) | external → DB | 3 | Owner-operator analytics over curated views | Raw SQL bypasses project RBAC, so use a SELECT-only role on analytics views. The reference servers are archived; avoid them |
| Domain: [bSDD MCP](https://github.com/JardiMargalefAgusti/bSDD-mcp) (community) ([009](topics/009-classification-mapping.md)), [pyp6xer-mcp](https://github.com/paulieb89/pyp6xer-mcp) (community) ([012](topics/012-cpm-p6-msproject.md)) | ERP ← external | 2 | Classification lookups, P6 file inspection | Community-maintained; pin versions |
| Browser: [Playwright MCP](https://github.com/microsoft/playwright-mcp) ([077](topics/077-browser-mcp.md)) | ERP ← external | 2 | Supplier and permit portals that have no API | Fragile and ToS-sensitive; optional plugin with a human review queue. The Puppeteer reference server is archived |
| [Filesystem MCP](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) ([072](topics/072-filesystem-mcp.md)) | local | 2 | Desktop users reading local tender folders alongside the ERP MCP server | No ERP code needed beyond docs |
| [GitHub MCP](https://github.com/github/github-mcp-server) ([073](topics/073-github-mcp.md)) | dev | 2 | Maintainer triage; GitHub Releases as the module-update registry | Not end-user facing |

---

## 5. Suggested sequencing

1. **Core plumbing:**
   - build `connector_core` (OAuth store, sync cursor, external links, inbound webhooks, retry queue);
   - harden webhooks and add the event catalog ([029](topics/029-automation-webhooks.md));
   - fix the ICS feed auth ([050](topics/050-calendar.md)).
2. **ERP MCP server** ([071](topics/071-erp-as-mcp-server.md)), together with prompt caching ([067](topics/067-prompt-caching.md)) to keep assistant costs down.
3. **Money:**
   - QuickBooks Online, then Xero;
   - e-invoicing for the DACH/EU market;
   - Stripe/Mollie payment links.
4. **Documents:** the cloud-drive layer with OneDrive/SharePoint and Google Drive first, then Dropbox and Box. Add inbound email → RFI/correspondence and e-signature for change orders and proposals.
5. **Field:** event-bus wiring for Slack/Teams approvals and WhatsApp/Telegram bots, plus weather evidence for daily reports.
6. **MCP client** in `erp_chat` with allowlists, then the communication, search and Workspace MCPs.
7. **On demand:** Procore, ACC, Bluebeam Studio and payroll, only when a user segment asks for them.

Each step should ship with its own validation rules. Examples: "synced bill has a cost code", "e-invoice passes KoSIT", "imported drawing revision is newer than the current one". This keeps the project rule that every import passes validation.
