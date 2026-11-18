# 032. Xero Accounting Integration (contacts, invoices, bills, tracking categories / projects)

## What it does
The ERP would sync its commercial data with Xero, a cloud accounting package that many small contractors in AU, NZ, UK and other markets use:
- **Contacts**: clients, subcontractors and suppliers sync in both directions with Xero Contacts.
- **Sales invoices**: progress claims and invoices from the `finance` module are pushed to Xero as `ACCREC` invoices.
- **Bills**: supplier and subcontractor invoices are pushed as `ACCPAY` invoices. Purchase orders could later sync too.
- **Payments**: payment status comes back from Xero, so the ERP's invoice status and cash-flow views stay correct without double entry.
- **Tracking categories / Projects**: each ERP project maps to a Xero tracking option (for example a "Job" category), so the P&L can be split per job inside Xero. The Xero Projects API (time and cost tracking) is an optional second step.

The estimator or PM keeps working in the ERP and the bookkeeper keeps working in Xero. Nobody has to retype invoices.

## Already in the codebase (with file paths)
- `backend/app/modules/finance/models.py`: `Invoice` (with `invoice_direction`, `contact_id`, `currency_code`, `tax_amount`, `retention_amount`, `status`, `metadata_` JSON), `InvoiceLineItem`, `Payment` and `ProjectBudget`. This already covers both receivable and payable documents.
- `backend/app/modules/finance/router.py`: Excel export of invoices and budgets (`/invoices/export/`). This is the only route to accounting software today, and it is manual.
- `backend/app/modules/contacts/models.py`: the `Contact` entity that would map to Xero Contacts.
- `backend/app/modules/integrations/`: messaging connectors only (Slack, Teams, Telegram, WhatsApp, Discord, email). Nothing for accounting.
- A grep for "xero" across `backend/app` and `frontend/src` finds nothing. The gap is a complete connector: OAuth2, mapping, sync jobs and conflict handling.

## Who it helps and how much
- Small contractors and estimating firms already on Xero benefit most. Retyping invoices and bills is a weekly chore, and errors there cause cash-flow surprises.
- Job-level P&L in Xero through tracking categories is something small firms usually build by hand in spreadsheets.
- Bookkeepers and external accountants can stay in Xero, which makes the ERP much easier to adopt.
- Value is high in Xero-heavy regions (AU/NZ/UK) and lower in DACH or the US, where DATEV or QuickBooks dominate. That argues for a generic accounting-connector interface with Xero as the first adapter.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** A new module `backend/app/modules/xero_connector/` (manifest `oe_xero`, depends on `oe_finance` and `oe_contacts`):
- **Auth**: an OAuth2 authorization-code flow with a stored token set. Access tokens last 30 minutes and refresh tokens 60 days, so refresh before each sync. Tokens are stored encrypted and scoped per tenant. A "Custom Connection" (client-credentials grant) is the option for single-organisation self-hosters.
- **Mapping tables**: `oe_xero_link (entity_type, local_id, xero_id, last_synced_at, hash)`, plus config for the account code, tax-rate mapping and the tracking category used as "Job".
- **Sync**: subscribe to event-bus events (`finance.invoice.approved`, `contacts.contact.updated`) to push changes. Pull payments on a schedule, or through Xero webhooks where available. Run all calls in background tasks and respect the 60 calls/min and 5,000 calls/day per-organisation limits, using batched endpoints.
- **Validation**: add rules such as "contact has a Xero mapping", "tax code mapped", "account code set" and "currency supported" before a push, in line with the validation-first principle.
- **Frontend**: a settings page (connect/disconnect, mappings) and a sync-status badge on invoices.
- A later refactor could pull out an `AccountingProvider` interface, so QuickBooks or DATEV adapters can reuse the same plumbing.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **xero-python SDK**, the official SDK: https://github.com/XeroAPI/xero-python. MIT. Covers the Accounting, Projects, Files, Assets and Payroll APIs, plus the OAuth2 helpers.
- **Xero MCP Server**, the official one: https://github.com/XeroAPI/xero-mcp-server. MIT, Node.js. It has tools for contacts, invoices, credit notes, payments, quotes and tracking categories (list/create/update), and supports custom-connection or bearer-token auth. It has no dedicated bill tools and no Projects tools. It could be exposed to `erp_chat`, or used as a reference.
- **Xero API pricing**: since March 2026 app partners pay under tiered plans based on connections and data egress, per https://developer.xero.com/faq/pricing-and-policy-updates and https://developer.xero.com/pricing. Secondary sources say the entry Starter tier is free with a lower daily call cap, and that custom connections are treated differently. I could not open the official pricing page from this environment, so check the current tier limits there before committing. Note also that each self-hosted install registers its own Xero app, which keeps costs per user.
- **Unified accounting APIs** (Apideck, Codat, Chift) are commercial and paid, and they cover Xero plus other ledgers. They don't fit the "lightweight, no lock-in" principle, so treat them as optional only.

## Priority: 4/5 — Removes double entry for the many small contractors who keep their books in Xero, using an MIT SDK and an existing finance model; worth doing behind a generic accounting interface because value varies by region.

## Sources
- https://github.com/XeroAPI/xero-python
- https://github.com/XeroAPI/xero-mcp-server
- https://developer.xero.com/pricing
- https://developer.xero.com/faq/pricing-and-policy-updates
- https://developer.xero.com/faq/limits
- https://www.accountingtoday.com/news/xero-shifts-to-tiered-pricing-model-for-developers
- https://apideck.com/blog/xero-api-pricing-and-the-app-partner-program
