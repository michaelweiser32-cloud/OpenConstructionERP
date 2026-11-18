# 031. QuickBooks Online integration (customers, invoices, bills, job costing classes)

## What it does
Two-way sync between OpenConstructionERP and QuickBooks Online (QBO), which holds the general ledger for many small US/CA/UK/AU contractors. The minimum useful scope:
- **Customers / Vendors**: push `contacts` (clients and subcontractors/suppliers) to QBO `Customer` and `Vendor`, and keep the QBO Id as an external reference.
- **Invoices (AR)**: push finance invoices and progress-billing applications as QBO `Invoice`, then pull `Payment` status back.
- **Bills (AP)**: pull vendor `Bill` lines so posted costs become "actual" cost on the job.
- **Job costing**: map each project to a QBO sub-customer or `Class` (and optionally `Department`/location), and map cost codes to `Item`/`Account`. QBO transactions carry a `ClassRef` at line or transaction level. Bill expense lines also carry a `CustomerRef` for job costing and billable expenses. This lets a bill posted in QBO roll up to the right project and cost code in the ERP.

## Already in the codebase (with file paths)
- `backend/app/modules/finance/models.py`: `Invoice` (with `invoice_direction` and `contact_id`), `InvoiceLineItem`, `Payment` and `ProjectBudget`. These are the natural sources and sinks for sync.
- `backend/app/modules/contacts/`: client and vendor master data.
- `backend/app/modules/integrations/models.py`: `IntegrationConfig` (a JSON `config` per connector), `WebhookEndpoint` and `WebhookDelivery`. Today these cover chat and notification connectors only (Slack, Teams, Telegram, Discord, WhatsApp, email).
- `backend/app/modules/costmodel/` and `docs/research/topics/020-job-costing.md`: that report already lists "no accounting sync (QuickBooks or Xero)" as a gap.
- **Gap:** a grep finds no QuickBooks, Intuit or OAuth2 accounting code anywhere. Nothing maps external IDs, stores refresh tokens, or reconciles sync conflicts.

## Who it helps and how much
High value for small US/CA GCs and trade subcontractors already on QBO. They will not switch ledgers, so without sync the ERP means double entry of every invoice and bill. Pulling bills by Class or Customer turns QBO into the source of actual cost for budget vs actual and cost-to-complete. Pushing invoices removes re-keying of progress bills. Bookkeepers keep working in QBO, and estimators and PMs work in the ERP. It matters less for DACH users, who are more likely on DATEV or lexoffice.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium** for customers, vendors, invoices, payments, bills and classes. The OAuth app, token refresh, idempotency and mapping UI are the bulk of the work.
- New module `backend/app/modules/accounting_qbo/` with a `manifest.py` that depends on `oe_finance` and `oe_contacts`. It contains `models.py` (`QboConnection` with realm_id and an encrypted refresh token; `ExternalRef` mapping entity_type, local_id, qbo_id and SyncToken; `QboMapping` linking project to Class/Customer and cost code to Item/Account), plus `service.py` and `router.py` (OAuth connect/callback, manual sync, mapping CRUD).
- Outbound: subscribe via `app/core/events.py` to `finance.invoice.approved` and `contacts.created`/`updated`, and enqueue a push (Celery, or in-process in dev).
- Inbound: QBO webhooks (`WebhookEndpoint` pattern) plus a periodic Change Data Capture poll for Bill, Payment and Purchase. Write actual cost into `costmodel`/`finance` budgets.
- Validation rules (required by the project rules): project has no Class mapping; invoice total does not match the QBO total; bill line has no Customer/Class; duplicate vendor.
- An optional `erp_chat/tools.py` tool can answer "AR aging" style questions from synced data.
- A generic accounting abstraction (QBO first, Xero later) avoids lock-in.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **QBO Accounting API (REST, OAuth 2.0)**: https://developer.intuit.com/app/developer/qbo/docs/api/accounting/most-commonly-used/account. The Intuit App Partner Program meters "CorePlus" (mostly data-out) calls. According to secondary sources, the free Builder tier allows unlimited Core calls and caps CorePlus at 500k/month. Paid tiers (Silver/Gold/Platinum) add credits and overage fees. I could not fetch Intuit's FAQ from this environment to confirm exact fees.
- **Class tracking docs**: https://developer.intuit.com/app/developer/qbo/docs/workflows/categorize-income-and-expenses
- **python-quickbooks**: https://github.com/ej2/python-quickbooks, MIT. Covers Customer, Invoice, Bill, Class, CDC and batch.
- **intuit-oauth** (official): https://github.com/intuit/oauth-pythonclient, Apache-2.0.
- **Official Intuit QBO MCP server**: https://github.com/intuit/quickbooks-online-mcp-server. TypeScript, runs locally over stdio with OAuth, and covers about 29 entities including Customer, Invoice, Bill, Vendor and Class, plus 11 reports. The README says MIT while the GitHub sidebar says Apache-2.0; check the LICENSE file. It suits ad-hoc AI queries, not production sync.
- **Unified APIs** (paid, closed source): Apideck and Codat. They help if Xero, Sage and others are also needed.
- Not verified: a premium QBO Projects API (named in third-party articles). The design above uses sub-customers and Classes, which work on the standard API.

## Priority: 5/5 — Accounting sync is the top adoption blocker for small US contractors, and existing finance/contacts models make it a Medium build with high return.

## Sources
- https://github.com/intuit/quickbooks-online-mcp-server
- https://blogs.intuit.com/?p=35282
- https://developer.intuit.com/app/developer/qbo/docs/get-started/partner-faq
- https://www.apideck.com/blog/quickbooks-api-pricing-and-the-intuit-app-partner-program
- https://hotglue.com/blog/how-to-lower-your-coreplus-quickbooks-api-usage
- https://developer.intuit.com/app/developer/qbo/docs/workflows/categorize-income-and-expenses
- https://cdn.cdata.com/help/RNN/py/pg_table-billlineitems.htm
- https://github.com/ej2/python-quickbooks
- https://github.com/intuit/oauth-pythonclient
- https://support.procore.com/products/online/user-guide/company-level/erp-integrations/qbo/quickbooks-online-detailed-data-mapping
