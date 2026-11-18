# 033. Sage integrations (Sage 50, Sage Intacct, Sage Accounting / Business Cloud, Sage 100 Contractor / Sage 300 CRE)

## What it does
Pushes approved estimating/ERP data (contacts, purchase orders, supplier bills, client invoices, payments, job-cost budgets by cost code) from OpenConstructionERP into the Sage accounting product a contractor already runs, and pulls back posted actuals and payment status. The "Sage" brand covers very different products with very different integration surfaces:

| Product | Target market | Integration surface (verified) |
|---|---|---|
| Sage Accounting (formerly Business Cloud Accounting) | UK/IE/CA micro & small | Public REST API v3.1, OAuth2, single host `api.accounting.sage.com/v3.1` |
| Sage Intacct (+ Intacct Construction) | US/UK/AU mid-market | XML Web Services + newer REST API (some objects still flagged beta/uncertified); construction objects for project / task / cost type; official read-only MCP server ("AI Gateway") announced late 2025 |
| Sage 50 US | US small | No web API; 32-bit .NET SDK that only runs on the Windows PC where Sage 50 is installed |
| Sage 50 UK/IE (Accounts) | UK small | No REST API; COM-based Sage Data Objects (SDO), needs paid UK Developer Programme membership |
| Sage 100 Contractor / Sage 300 CRE | US small–mid contractors | No public documented web API; official path is Sage Construction Management "AccountingLink"; otherwise third-party (hh2, unified API vendors) |

## Already in the codebase (with file paths)
- No Sage, Intacct, QuickBooks, Xero or DATEV connector exists (grep over `backend/app` and `frontend/src` finds none).
- `backend/app/modules/finance/models.py` defines `Invoice`, `InvoiceLineItem`, `Payment`, `ProjectBudget`, `EVMSnapshot` — the natural source records to sync.
- `backend/app/modules/finance/router.py` offers Excel exports of invoices/budgets and CSV budget import — today the only "bridge" to accounting is manual file export.
- `backend/app/modules/integrations/` holds messaging connectors (Slack, Teams, Telegram, WhatsApp, Discord, email) with a `models.py`/`service.py` pattern that an accounting connector could reuse for credential/config storage.
- `backend/app/modules/procurement/` and `contacts/` supply POs and vendors/customers.

## Who it helps and how much
- UK/IE/CA micro contractors on Sage Accounting: high — removes double entry of invoices and supplier bills.
- US mid-size contractors on Sage Intacct Construction: high value per customer (cost-code budgets and job-cost actuals map directly to project/task/cost type), but fewer small businesses.
- Sage 50 (US and UK) users: large installed base among small firms, but integration is desktop-bound; a CSV/IIF-style import file is the realistic option.
- Sage 100 Contractor / 300 CRE users: real demand, but no public API — only file import or paid third-party middleware.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch)
**Medium overall** (S for export files, M for Sage Accounting REST, M–L for Intacct construction mapping).
- New module `backend/app/modules/accounting_sage/` (manifest `depends=["oe_finance","oe_contacts","oe_procurement"]`) or a provider inside a generic `accounting_sync` module shared with QuickBooks/Xero.
- Provider interface: `push_contact`, `push_invoice`, `push_bill`, `pull_payments`, `push_budget(cost_codes)`; OAuth2 tokens stored encrypted per tenant.
- Subscribe to finance events (invoice approved, payment recorded) via `app/core/events.py`; sync runs as background task with idempotency keys and a sync-log table.
- Validation rules (per project rules): every line has GL account/tax code mapped, cost code exists in target, totals match — run before push.
- Sage 50 / 100 Contractor / 300 CRE: export-file generators (CSV in each product's import layout) — no live sync.
- MCP: Sage's own Intacct MCP server is read-only; `erp_chat/tools.py` could consume it for "what did we actually spend on job X" questions, with human-confirmed writes staying in our REST provider.

## Building blocks (free/open-source libs, APIs, MCP servers)
- Sage Accounting API v3.1 — https://developer.sage.com/accounting — free developer account; end user needs a Sage subscription.
- Sage Intacct REST API / OpenAPI (projects, construction) — https://developer.sage.com/intacct/docs/openapi/z-indexes/index-cre — Web Services access needs a Sage-issued sender ID (partner/subscription terms apply).
- `sageintacctsdk` (Fyle, Python, XML Web Services) — https://github.com/fylein/sageintacct-sdk-py — open source (check repo license); `sageintacctrestsdk` on PyPI for REST/OAuth2.
- Sage Intacct AI Gateway / MCP server (official, read-only, admin-enabled) — https://www.sage.com/en-us/sage-business-cloud/intacct/product-capabilities/platform/ai-gateway/ — included per Sage terms; endpoint details not verified here.
- CData Intacct MCP server (third-party, read-only, commercial driver) — https://www.cdata.com/drivers/intacct/mcp/
- Unified APIs (Apideck, Codat, Nango) cover several Sage products — commercial, per-connection pricing; useful to avoid desktop SDKs but add a paid dependency.
- No verified official MCP server exists for Sage Accounting, Sage 50, Sage 100 Contractor or Sage 300 CRE.

## Priority: 3/5 — Real pain for small contractors, but Sage is fragmented; ship Sage Accounting REST + Intacct and file exports for desktop Sage behind a generic accounting-sync interface shared with QuickBooks/Xero.

## Sources
- https://developer.sage.com/accounting/guides/concepts/overview
- https://developer.sage.com/api/accounting/api
- https://developer.sage.com/intacct/docs/openapi/z-indexes/index-cre
- https://developer.sage.com/intacct/docs/openapi/cre/construction.standard-cost-type/tag/Standard-cost-types
- https://developer.sage.com/intacct/docs/developer-portal/release-notes/2024-r1
- https://www.sage.com/en-us/sage-business-cloud/intacct/product-capabilities/platform/ai-gateway/
- https://www.cdata.com/drivers/intacct/mcp/
- https://github.com/fylein/sageintacct-sdk-py
- https://pypi.org/project/sageintacctrestsdk/1.3.0/
- https://www.apideck.com/blog/how-to-integrate-with-the-sage-50-us-api
- https://www.codat.io/blog/a-developers-guide-to-building-a-sage-50-integration/
- https://help.sagecm.intacct.com/Content/AccountingLink/CLSage300CRE/IntegrationOverview/IntegrationOverview.htm
- https://nango.dev/docs/api-integrations/sage-300-cre
