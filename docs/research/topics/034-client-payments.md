# 034. Client payments: payment links, ACH/SEPA and deposits for invoices

## What it does
Lets a contractor send an outgoing invoice (progress bill, deposit request, final bill) with a "Pay now" link. The client pays by card, ACH (US) or SEPA Direct Debit/bank transfer (EU). A provider webhook then marks the invoice paid in the ERP, so nobody re-keys it. Typical small-contractor uses: a 10-50% mobilization deposit before work starts, progress payments that are retainage-aware, and saved bank mandates for repeat clients. Bank rails matter because card fees (about 3%) on a large construction invoice are much higher than capped ACH fees.

## Already in the codebase (with file paths)
- `backend/app/modules/finance/models.py`: `Invoice` (has `invoice_direction`, `due_date`, `currency_code`, `retention_amount`, `amount_total`, `status`, `payment_terms_days` and a `metadata_` JSON field) and `Payment` (has `payment_date`, `amount`, `currency_code`, `exchange_rate_snapshot`, `reference`).
- `backend/app/modules/finance/router.py`: `list_payments`, `create_payment`, `approve_invoice`, `pay_invoice`, and an invoice export. All payments are recorded by hand.
- `backend/app/core/crypto.py`: could encrypt stored provider API keys.
- `backend/app/modules/integrations/`: Slack, Teams, Telegram, WhatsApp, Discord and email. These could notify the team when a payment succeeds.
- **Gap:** there is no payment provider SDK, no payment-link or checkout session, no inbound webhook endpoint or signature check, no deposit or partial-payment request object, and no "invoice viewed" or "payment failed" state. A grep finds no references to Stripe, Mollie, GoCardless or PayPal.

## Who it helps and how much
- **Small general contractors and specialty trades:** high value. Getting a deposit before buying materials reduces cash-flow risk. A pay-link shortens days-sales-outstanding (DSO), and paid status updates automatically.
- **Estimators and owners in a one-to-five-person office:** no manual reconciliation of bank statements against invoices.
- **Clients:** one-click ACH or SEPA payment. The fee is capped, so contractors are less tempted to add card surcharges.
- QuickBooks Payments charges 1% on ACH, and its help pages say customers cannot make partial ACH payments on invoices. A native integration that supports partial and deposit payments is a real differentiator for construction billing.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** The work is a new `payments_gateway` module that depends on `oe_finance` and `oe_contacts`, with provider adapters behind one interface.
- **`models.py`:** `PaymentProviderConfig` (per tenant, with the API key encrypted by `core/crypto.py`) and `PaymentRequest` (`invoice_id`, `kind` = deposit/progress/final, `amount`, `provider`, `external_id`, `url`, `status`, `expires_at`).
- **`service.py`:** `create_link(invoice, amount)` calls Stripe Checkout or Payment Links, a Mollie Payment Link, or a GoCardless Billing Request.
- **`router.py`:** `POST /webhooks/{provider}` verifies the signature, is idempotent on the provider event id, creates a `finance.Payment` row, and emits a `finance.invoice.paid` event on the event bus. Notifications and integrations subscribe to that event.
- **Validation rules:** the link amount must not exceed the open balance (`amount_total` minus `retention_amount` minus payments already received); the currency must match; a deposit must be at most a configurable percentage of the contract value.
- **Frontend:** a "Request payment" button on the invoice, a status chip, and provider settings.
- The AI or chat layer may draft a reminder but must not move money. That fits the "human-confirmed" principle.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Stripe API, Payment Links and Invoicing**
  - SDK: `stripe-python` (MIT, https://github.com/stripe/stripe-python).
  - ACH Direct Debit: 0.8%, capped at $5 (https://stripe.com/gb/payments/us-bank-payments).
  - Stripe Invoicing adds 0.4-0.5% per paid invoice. That figure comes from third-party summaries.
- **Stripe MCP server:** official. It runs locally via `@stripe/mcp` or remotely at `mcp.stripe.com`, and has tools such as `create_payment_link` and `create_invoice`. It is useful for an ops assistant, not as the core integration (https://docs.stripe.com/mcp; repo https://github.com/stripe/ai).
- **Mollie:** card and SEPA in the EU, with a Payment Links API.
  - SDK: `mollie-api-python` (BSD).
  - SEPA Direct Debit costs about €0.35 per transaction (https://www.mollie.com/payments/direct-debit).
  - Official MCP server: https://docs.mollie.com/docs/mollie-mcp-server.
- **GoCardless:** bank-debit mandates (SEPA, Bacs, ACH) for recurring and progress payments.
  - SDK: `gocardless-pro-python` (MIT).
  - Sources disagree on pricing; one gives SEPA at about 1% + fee, capped.
  - I could not confirm an official MCP server. Only community servers were verified, for example https://glama.ai/mcp/servers/@jmceleney/gocardless-mcp.
- **PayPal:** has an official MCP server with `create_invoice` and `send_invoice` tools (https://paypal.gitbook.com/agent-toolkit-and-mcp-server/mcp-server/mcp-server-tools).
- **Alternative with no provider:** EPC QR codes (SEPA "GiroCode") printed on the invoice PDF. This is free and needs no API, but there is no automatic paid status.

## Priority: 4/5 — cash flow is the main pain point for small contractors, and finance already has the Invoice and Payment models, so the gap is a well-scoped adapter module
Not 5 because it requires provider accounts, KYC and webhook hosting. Self-hosted single-VPS users need a public URL to receive webhooks, so the module must work without the provider integration.

## Sources
- https://stripe.com/gb/payments/us-bank-payments
- https://docs.stripe.com/mcp
- https://github.com/stripe/ai
- https://dodopayments.com/blogs/stripe-invoicing-fees-explained/
- https://www.mollie.com/payments/direct-debit
- https://docs.mollie.com/docs/mollie-mcp-server
- https://glama.ai/mcp/servers/@jmceleney/gocardless-mcp
- https://paypal.gitbook.com/agent-toolkit-and-mcp-server/mcp-server/mcp-server-tools
- https://quickbooks.intuit.com/learn-support/en-us/help-article/refund-payments/let-customers-pay-invoices-ach-bank-payment-fee/L2pPurNTw_US_en_US
- https://quickbooks.intuit.com/payments/legal/toc102017/standard-pricing-schedule-sep2023/
