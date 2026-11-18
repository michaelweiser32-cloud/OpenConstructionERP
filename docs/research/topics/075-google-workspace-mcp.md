# 075. Google Workspace MCP servers (Drive, Gmail, Calendar, Sheets)

## What it does
Lets the ERP's AI assistant use a small firm's Google Workspace data through the Model Context Protocol (MCP), with a person confirming each action. Examples:
- "Find the latest structural drawings the architect shared in Drive and attach them to project X" (Drive).
- "Summarise this week's subcontractor quote emails and draft an RFQ follow-up" (Gmail, saved as a draft only).
- "Pull the unit rates from the supplier price sheet into the cost database" (Sheets).

The feature can work in two directions, and both are worth building:
1. **The ERP as an MCP client.** `erp_chat` calls Google's MCP servers, or a self-hosted one, as extra tools.
2. **The ERP as an MCP server.** The existing `erp_chat/tools.py` handlers are exposed over MCP. A user's own agent (Claude, Gemini CLI and others) can then join ERP data with their Google MCP servers without the ERP holding Google tokens at all.

This topic covers only the MCP or agent layer. Deterministic connectors are separate topics: Drive import/export is 041, inbound mail is 046 and calendar sync is 050.

## Already in the codebase (with file paths)
- There is **no MCP code** in `backend/app` or `frontend/src`. A grep for "mcp" or "model context protocol" finds nothing.
- `backend/app/modules/erp_chat/tools.py` already has AI tool handlers that check permissions (`handle_get_boq_items`, `handle_search_documents`, `handle_create_boq_item`, `handle_run_validation`, ...). These are a ready-made tool surface to publish as an MCP server.
- `backend/app/modules/integrations/router.py` (`/calendar/{project_id}.ics/`) has a read-only ICS feed that users can subscribe to from Google Calendar. It authenticates by API-key prefix only (see 050).
- There is no Google OAuth, Gmail, Drive or Sheets API code anywhere.

## Who it helps and how much
- Small firms on Google Workspace where the estimator or PM is also the admin, and quotes, drawings and schedules sit in Gmail, Drive and Sheets.
- **Value: Medium.** It saves time on ad-hoc lookups and drafts. It does not replace the deterministic connectors in 041, 046 and 050, which carry the audit trail. The value depends on users already using AI agents. Firms on Microsoft 365 get nothing from it.

## Implementation effort
**Medium.** Touches `erp_chat`, `ai` and `integrations`, plus one new optional plugin module (`oe_mcp`).
- **Phase A, ERP as an MCP server (small to medium):** a new module `backend/app/modules/mcp_server/` with `manifest.py` (`auto_install=False`) and a router mounted at `/api/v1/mcp/`. It uses the official MCP Python SDK over streamable HTTP and wraps the existing `tools.py` handlers. Authentication uses the existing API keys or JWT scoped per user, and the same RBAC checks as chat. Write tools (`create_boq_item`) are tagged destructive, so clients ask the user to confirm.
- **Phase B, ERP as an MCP client (medium):** an `McpToolProvider` in `erp_chat` that the admin configures with a server URL and OAuth client. It merges remote tools into the LLM tool list with a per-tool allowlist and read-only by default. Every remote result goes into the AI proposal flow ("AI suggests, human confirms") and raises an `erp_chat.external_tool_called` event for audit. Google refresh tokens are encrypted with `core/crypto.py`.
- **Validation:** any data from Sheets or Drive that turns into cost items or BOQ positions goes through the normal import validation pipeline.
- **Risks:** Google's hosted servers are in preview, and prompt injection through email content is a real threat. Treat email bodies as untrusted data, and allow sending or sharing only after explicit confirmation.

## Building blocks
- **Google Workspace MCP servers (official, hosted).** Remote endpoints such as `gmailmcp.googleapis.com`, `drivemcp.googleapis.com`, `calendarmcp.googleapis.com` and `chatmcp.googleapis.com`. Per Google's configuration guide and third-party docs they are in **Developer Preview** and need enrollment; tool calls fail until the project is enrolled. I could not fetch Google's pages from this environment, so I could not confirm whether a hosted Sheets MCP server is generally available. Third-party sources say the Gmail server creates drafts but does not send. No separate MCP price is listed. https://developers.google.com/workspace/guides/configure-mcp-servers
- **taylorwilsdon/google_workspace_mcp (MIT, about 3.5k stars).** Self-hostable. Covers Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Tasks, Contacts and Chat. Supports stdio or streamable HTTP, OAuth 2.1 multi-user auth, tool tiers and a `--read-only` mode. It is the most practical option today for self-hosters. https://github.com/taylorwilsdon/google_workspace_mcp
- **MCP Python SDK** (MIT): https://github.com/modelcontextprotocol/python-sdk
- **Google Sheets API v4.** Free within quotas of 300 read and 300 write requests per minute per project and 60 per user. A localized version of the limits page says overage billing is planned for 2026, so check before relying on free use. https://developers.google.com/sheets/api/limits

## Priority: 3/5 — the cheap win is exposing the existing erp_chat tools as an MCP server, which works with any Google or other MCP client; consuming Google's hosted servers waits on preview status and safety design.

## Sources
- https://developers.google.com/workspace/guides/configure-mcp-servers
- https://workspaceupdates.googleblog.com/2026/05/agent-tools-and-security-updates-for-workspace-developers.html
- https://docs.aembit.io/ai-guide/mcp/identity-gateway/supported-servers/google-workspace/
- https://github.com/taylorwilsdon/google_workspace_mcp
- https://github.com/modelcontextprotocol/python-sdk
- https://developers.google.com/sheets/api/limits
- https://cloud.google.com/blog/products/ai-machine-learning/google-managed-mcp-servers-are-available-for-everyone
