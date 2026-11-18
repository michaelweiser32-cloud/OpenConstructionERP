# 079. Communication MCP servers (Slack, Gmail, Twilio, WhatsApp)

## What it does
Model Context Protocol (MCP) servers let an AI assistant (the ERP's own `erp_chat`, or an external client such as Claude or Cursor) read and send messages in the channels a small contractor already uses. There are two directions:
1. **Outbound (ERP as MCP client):** the in-app assistant drafts an RFI follow-up email, posts a site-delay note to Slack, or texts a subcontractor, with a human confirming before anything is sent.
2. **Inbound (ERP as MCP server):** the ERP's own tools (BOQ, RFIs, schedule, punch list) are exposed over MCP, so an assistant already connected to Slack or Gmail can combine "read this supplier email" with "update the quote in the ERP".

## Already in the codebase (with file paths)
- Outbound, one-way notification connectors over plain HTTP (no MCP): `backend/app/modules/integrations/slack.py` (incoming webhook, Block Kit), `whatsapp.py` (Meta Cloud API v20.0 template messages, marked "Coming Soon"), `teams.py`, `telegram.py`, `discord.py`, and `email_service.py` (a shim over `backend/app/core/email`).
- `backend/app/modules/integrations/router.py`: per-user integration configs, a test-send endpoint, outbound webhooks, and an ICS calendar feed.
- `backend/app/modules/erp_chat/tools.py`: about 16 LLM tool schemas (get_boq_items, get_schedule, run_validation, create_boq_item, search_documents...). These are a good basis for an MCP server.
- **Gap:** I found no MCP client or server code and no `mcp` dependency. The connectors are send-only: nothing reads Slack threads, email inboxes or inbound WhatsApp replies. There is no Twilio/SMS connector.

## Who it helps and how much
- **Small GC or estimator (1-10 people):** high value. Most RFIs, quotes and subcontractor coordination happen in email and WhatsApp, not in the ERP. Turning a supplier email into a costed quote line, or a WhatsApp site photo into a punch item, saves re-keying every day.
- **Field crews:** SMS (Twilio) and WhatsApp reach people who will not install an app.
- **Limits:** the official Slack and Gmail MCP servers are aimed at AI clients run by the user, and Gmail's server is still in developer preview. For server-side automation the native REST APIs stay more reliable.

## Implementation effort
**Medium.** It touches `integrations`, `erp_chat` and possibly a new `mcp_gateway` module.
- **Step 1 (S):** expose the `erp_chat/tools.py` tools as an MCP server with the official Python SDK (FastMCP), mounted at `/api/v1/mcp/` with a Streamable HTTP app. Authenticate with the existing JWT/API keys and check permissions per tool. Write tools stay behind a confirmation step (AI-augmented, human-confirmed). This gives any MCP client, including ones already connected to Slack or Gmail, access to the ERP.
- **Step 2 (M):** add a Twilio SMS connector and inbound webhooks for WhatsApp, Twilio and email to `integrations`. Inbound messages are published on the event bus (`core/events.py`) as `integrations.message_received`, and modules such as `rfi`, `punchlist` and `fieldreports` subscribe through hooks to suggest records.
- **Step 3 (optional):** let `erp_chat` act as an MCP client of remote servers (Slack, Gmail) using per-user OAuth tokens. It should be off by default to keep the core light.
- **Validation:** add rules for phone/E.164 format, opt-in or consent flags, and a WhatsApp template-approved check.

## Building blocks
- **MCP Python SDK** (`mcp`, includes FastMCP), MIT: https://github.com/modelcontextprotocol/python-sdk. FastAPI mounting is not fully documented yet (see PR #1712).
- **Slack MCP server (official, hosted)** at `https://mcp.slack.com/mcp`, using OAuth and Streamable HTTP. Only directory-published or internal apps can use it, and the API is free within Slack rate tiers: https://docs.slack.dev/ai/mcp-server/
- **Gmail remote MCP server (Google)** at `https://gmailmcp.googleapis.com/mcp/v1`. It is in Workspace Developer Preview, and sources disagree on whether it can send email or only create drafts (I could not open the tool reference to check): https://developers.google.com/workspace/gmail/api/reference/mcp
- **Twilio MCP (`twilio-labs/mcp`, npm `@twilio-alpha/mcp`)**, MIT, alpha. It wraps Twilio's public API, and `--services` limits which APIs are exposed. Usage is pay-as-you-go: https://github.com/twilio-labs/mcp, https://www.twilio.com/en-us/sms/pricing/us
- **WhatsApp:** I could not verify an official Meta MCP server. The community `lharries/whatsapp-mcp` (MIT) uses the unofficial WhatsApp Web multidevice protocol (whatsmeow) on a personal account. That carries terms-of-service risk, so it is not suitable to ship. Use the official Cloud API instead, which bills per delivered template message by market and category (rate cards are revised quarterly): https://developers.facebook.com/docs/whatsapp/pricing
- **Plain fallbacks:** stdlib `imaplib`/`smtplib` for any mailbox, and `slack_sdk` (MIT) for Events API inbound.

## Priority: 4/5 — Most of a small firm's project communication runs through email and WhatsApp. An ERP MCP server is cheap to build on the existing `erp_chat` tools, and inbound capture addresses the main gap. Third-party MCP servers are still preview or alpha, so they should be optional add-ons.

## Sources
- https://docs.slack.dev/ai/mcp-server/
- https://developers.google.com/workspace/gmail/api/reference/mcp
- https://developers.google.com/workspace/gmail/api/guides/configure-mcp-server
- https://github.com/twilio-labs/mcp
- https://www.twilio.com/en-us/sms/pricing/us
- https://github.com/lharries/whatsapp-mcp
- https://developers.facebook.com/docs/whatsapp/pricing
- https://github.com/modelcontextprotocol/python-sdk
- https://github.com/modelcontextprotocol/python-sdk/pull/1712
