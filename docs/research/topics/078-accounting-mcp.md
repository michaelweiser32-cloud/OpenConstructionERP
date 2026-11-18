# 078. Accounting MCP servers (QuickBooks, Xero, Stripe official MCPs)

## What it does
The three platforms a small contractor most often uses for books and payments now ship vendor-published Model Context Protocol (MCP) servers:

- **QuickBooks Online**: an open-source local (stdio) MCP server covering about 29 entities (Customer, Estimate, Invoice, Bill, Vendor, Item, Purchase Order, Payment, Time Activity, Attachable and more) plus about 11 reports (P&L, Balance Sheet, Aged AR/AP and others). Write, update and delete tools can each be switched off with an environment flag.
- **Xero**: `@xeroapi/xero-mcp-server`, MIT licence, about 51 tools. It covers contacts, invoices, quotes, payments, bank transactions, tracking categories, P&L and aged receivables/payables, and payroll timesheets.
- **Stripe**: a hosted remote server at `https://mcp.stripe.com` using OAuth, plus a local `@stripe/mcp` npm package. It covers customers, invoices, payment links, products and prices, refunds and balance.

For an estimating ERP, this means an AI assistant can turn an approved BOQ or tender into a QuickBooks or Xero estimate or invoice, post progress-billing invoices, pull aged receivables into project cash-flow views, and send a Stripe payment link for a deposit. Under the project's AI-augmented, human-confirmed rule, a person confirms every write.

## Already in the codebase (with file paths)
- `backend/app/modules/finance/models.py` has `Invoice` (with `invoice_direction`, `status` and `currency_code`), `InvoiceLineItem`, `Payment`, `ProjectBudget` and `EVMSnapshot`. This is a usable internal ledger, but it has no external IDs or sync state.
- `backend/app/modules/erp_chat/tools.py` holds the in-app LLM tool handlers (`handle_get_boq_items`, `handle_create_boq_item` and others). It uses its own tool registry and is not an MCP server or client.
- `backend/app/modules/integrations/` holds messaging connectors only (Slack, Teams, Telegram, WhatsApp, Discord, email).
- **Gap:** a grep of `backend/app` and `frontend/src` finds nothing for QuickBooks, Xero or Stripe, and no MCP code at all.

## Who it helps and how much
Small general contractors and estimators who already run their books in QuickBooks or Xero (QuickBooks mostly in the US, Xero mostly in the UK, AU and NZ). Today they re-key estimates into invoices and chase payments by hand. The main time saved is on double entry and on billing-to-cash. Stripe payment links help trades that take deposits. The value is high for US, UK and AU small businesses and lower in DACH, where DATEV and Lexoffice dominate and none of these MCPs apply.

## Implementation effort
**Medium. Modules touched:** `integrations` (or a new `accounting_sync` module), `finance` and `erp_chat`.

There are two complementary paths:
1. **MCP client in erp_chat (Small to Medium).** Add an optional MCP client using the Python `mcp` SDK. The tenant config holds the server command (QBO or Xero over stdio) or URL (Stripe remote). The client exposes the remote tools to the in-app assistant behind a confirmation step. Write tools stay disabled by default: QBO has `QUICKBOOKS_DISABLE_WRITE`, and an allow-list covers the others.
2. **Deterministic sync (Medium).** Add an `accounting_sync` plugin module with a manifest that depends on `oe_finance`. It adds an `external_ref` table (provider, remote_id, etag, last_synced) and subscribes to event-bus events such as `finance.invoice.approved`. It calls the vendor REST APIs directly, because MCP is aimed at agents, not reliable background sync. Validation rules check for missing tax codes, unmapped items or accounts, and currency mismatches before any push.

OAuth token storage needs encryption. For QBO production, the initial authorisation needs a public HTTPS callback.

## Building blocks
- **Intuit QuickBooks Online MCP server.** GitHub repo; the README says MIT but the sidebar shows Apache-2.0, so verify the LICENSE file. Its provenance needs checking too: the README's Acknowledgments say it is "based on" Intuit's server, so confirm the repo is Intuit-maintained. Local stdio, OAuth2. QBO API access requires an Intuit developer app. Intuit's App Partner Program meters some API calls; I did not verify current pricing.
- **Xero MCP server.** MIT, npm package `@xeroapi/xero-mcp-server`. Auth is a custom connection or a bearer token. Since March 2026, Xero API access is tiered: a free Starter tier with 5 connections, then paid Core, Plus, Advanced and Enterprise tiers (egress overage about 2.40 AUD per GB).
- **Stripe MCP.** Official, hosted at `mcp.stripe.com` with OAuth, or local `@stripe/mcp` with a restricted API key. The server itself is free; normal Stripe processing fees apply. I could not reach the official docs page from this environment, so its details come from search summaries.
- **Python MCP SDK** (`mcp`, MIT) for the client side.

## Priority: 3/5 — vendor MCPs remove most connector work, but they suit an AI-assistant layer more than core sync, and they only reach US, UK and AU users
Pushing invoices and estimates to accounting is high value for small businesses. Doing it via MCP is cheap, but the tools are still young, local-only for QBO and Xero, and region-limited. Ship the MCP client in erp_chat first, then a deterministic sync for QBO and Xero.

## Sources
- https://github.com/intuit/quickbooks-online-mcp-server
- https://github.com/XeroAPI/xero-mcp-server
- https://docs.stripe.com/mcp
- https://socket.dev/npm/package/@stripe/mcp
- https://developer.xero.com/faq/pricing-and-policy-updates
- https://www.accountingtoday.com/news/xero-shifts-to-tiered-pricing-model-for-developers
- https://github.com/modelcontextprotocol/python-sdk
