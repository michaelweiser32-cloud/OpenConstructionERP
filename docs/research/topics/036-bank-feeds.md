# 036. Bank feeds (Plaid, GoCardless Bank Account Data, open banking) for reconciliation

## What it does
Pulls bank-account transactions automatically from the bank, or imports statement files, and matches them against invoices and payments in the ERP. Incoming money gets marked against receivables (progress billings, retention releases) and outgoing money against payables (subcontractor and supplier invoices). There are two ways to get the data:
- **API feeds:** Plaid in the US, CA and UK/EU, or a PSD2 open-banking aggregator in Europe.
- **File import:** CAMT.053, MT940, OFX/QFX, or CSV statements. This works with every bank and needs no third-party contract.

## Already in the codebase (with file paths)
- `backend/app/modules/finance/models.py` has `Invoice`, `InvoiceLineItem`, `Payment` (`oe_finance_payment`, recorded manually against an invoice), `ProjectBudget` and `EVMSnapshot`.
- `backend/app/modules/finance/router.py` and `service.py` hold invoice and payment CRUD.
- **The gap:** a search of `backend/app` and `frontend/src` finds no bank-account model, no bank-transaction or statement import, no reconciliation and no aggregator client. `Payment` rows are entered by hand only.
- `backend/app/modules/integrations/` is the natural home for connector credentials and webhooks.

## Who it helps and how much
- **Who:** small contractors and estimating firms that bill on progress and pay many subcontractors.
- **What it saves:** auto-matching by amount, reference and invoice number turns hours of month-end work into minutes. It also shows cash position per project, which feeds the cash-flow and EVM views.
- **Limit:** most small firms already run accounting software (QuickBooks, Xero, DATEV) that has its own bank feeds. The value is therefore highest for firms that use this ERP as their main finance tool, or that want project-level cash tracking. It is medium for firms that already sync with an accounting package.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Overall: Medium.** File import alone is Small; live API feeds add a Medium layer on top.
- **New module `bank_feeds`.** Its `manifest.py` depends on `oe_finance` and `oe_integrations`. It has these models:
  - `BankAccount`
  - `BankTransaction`, holding the external id, booking date, amount, currency, counterparty, remittance text, raw JSONB and a status (unmatched, suggested or matched)
  - `ReconciliationMatch`, linking a transaction to an invoice or payment, with a confidence score
- **Provider adapter interface.** `fetch_transactions(account, cursor)` is implemented by `FileImportProvider` (CAMT/MT940/OFX/CSV), `PlaidProvider` (cursor-based `/transactions/sync` plus the `SYNC_UPDATES_AVAILABLE` webhook) and an `EnableBankingProvider` or other PSD2 adapter. Each provider is optional and loaded only when its credentials are configured.
- **Matching runs on the existing core pieces:**
  - The event bus raises `bank.transaction.imported`.
  - A matching service suggests matches by exact amount, invoice number found in the remittance text, counterparty-to-contact mapping and a date window.
  - A user confirms each match, and only then is a `Payment` created. This follows the project's "AI suggests, human confirms" rule.
- **Validation rules:** duplicate transaction id, currency mismatch, and a payment amount that exceeds the open invoice balance.
- **Frontend:** a reconciliation inbox with suggested matches, accept or reject, and bulk accept.
- **Security:** aggregator tokens are encrypted at rest; transaction data is personal and financial data under GDPR; PSD2 consent expires and must be renewed (typically every 90–180 days).

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Plaid Transactions API** (https://plaid.com/docs/transactions/). Commercial and usage-based; Sandbox is free; production plans are custom or through sales (https://plaid.com/docs/account/billing/). There is an official Python SDK, `plaid-python`.
- **Plaid MCP servers** (https://plaid.com/blog/ai-development-toolkit/):
  - A local server, `mcp-server-plaid`, for Sandbox and development work.
  - A remote Dashboard MCP server for production diagnostics.
  - Neither is a feed of end-user transactions. Community servers that wrap `/transactions/sync` exist (for example https://glama.ai/mcp/servers/laramarcodes/plaid-transactions-mcp), but they are unofficial and unvetted.
- **GoCardless Bank Account Data**, formerly Nordigen (https://developer.gocardless.com/bank-account-data/overview). Third-party reports say new signups closed in July 2025 (https://actualbudget.org/docs/advanced/bank-sync/gocardless/). It should not be the default for new deployments; existing accounts reportedly still work.
- **Enable Banking** (https://enablebanking.com/accounts-api). EU PSD2 aggregator. It is free only for evaluation or private personal use (https://enablebanking.com/terms); business use needs a commercial agreement. I could not verify a public price list.
- **Salt Edge** (https://saltedge.com/products/spectre). Commercial alternative; pricing is by quote.
- **Statement-file parsers (no aggregator needed):**
  - `mt940` (https://github.com/WoLpH/mt940). Open source with no runtime dependencies; confirm the license before vendoring.
  - `pycamt` (https://pypi.org/project/pycamt). CAMT.053 parser.
  - `bankstatementparser` (https://pypi.org/project/bankstatementparser). Covers CAMT, MT940, OFX and CSV, but it is a young project, so check its maintenance and license first.
  - There is a community MCP server, `camt053-mcp` (https://pypi.org/project/camt053-mcp/), which I could not verify.

## Priority: 3/5 — clear time-saver for firms using the ERP as their finance tool; start with file import, add API feeds later
File import (CAMT/MT940/OFX/CSV) plus matching suggestions is cheap, works with every bank and has no per-connection fees. Live API feeds have real costs, a contract and compliance burden, and region fragmentation, and many small firms already get bank feeds from their accounting software. Ship file import first and add Plaid or a PSD2 aggregator as an optional provider later.

## Sources
- https://plaid.com/docs/transactions/
- https://plaid.com/docs/account/billing/
- https://plaid.com/blog/ai-development-toolkit/
- https://developer.gocardless.com/bank-account-data/overview
- https://actualbudget.org/docs/advanced/bank-sync/gocardless/
- https://www.openbankingtracker.com/guides/free-open-banking-apis
- https://enablebanking.com/accounts-api
- https://enablebanking.com/terms
- https://github.com/WoLpH/mt940/
- https://pypi.org/project/bankstatementparser
