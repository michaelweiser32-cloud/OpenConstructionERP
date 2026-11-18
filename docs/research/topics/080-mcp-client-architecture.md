# 080. MCP client architecture inside erp_chat

## What it does
Lets the ERP chat assistant call tools from **external MCP (Model Context Protocol) servers**, alongside its own built-in ERP tools. Examples: a cloud-storage server, a calendar server, or an accounting server. An admin registers a server (URL + auth), picks which of its tools are allowed, and the chat loop merges those tools into the LLM tool list. The design has to cover four things: **transport** (Streamable HTTP for remote servers, stdio only for vetted local servers), **auth** (OAuth 2.1 per the MCP authorization spec, or static bearer tokens), **sandboxing** (SSRF guard, timeouts, result size caps, no arbitrary stdio commands), and **permissions** (per-tool allowlists, human approval for write tools, per-tenant/per-user scoping).

## Already in the codebase (with file paths)
- `backend/app/modules/erp_chat/service.py` runs a hand-rolled agent loop (`MAX_AGENT_ROUNDS`). It makes raw `httpx` calls to Anthropic and OpenAI, has a text-only fallback for other providers, and truncates tool results (`MAX_TOOL_RESULT_CHARS = 8000`).
- `backend/app/modules/erp_chat/tools.py` holds the **static** `TOOL_DEFINITIONS` / `TOOL_HANDLER_MAP` (about 17 internal tools). Each project-scoped tool runs a `_require_project_access` authorization check, and arguments go through validation helpers (`ToolAuthError`).
- `backend/app/core/url_safety.py` provides SSRF-safe URL validation, including validation after DNS resolution. It can be reused for MCP server URLs.
- `backend/app/core/crypto.py` stores secrets at rest with Fernet. It can be reused for MCP OAuth/bearer tokens.
- **Gap:** no MCP code exists anywhere (grep for "mcp" in `backend/app` returns nothing). There is no tool registry that can change at runtime, no per-tool approval step, and no server/credential model.

## Who it helps and how much
Small firms already use SaaS tools (storage, calendars, accounting, CRM) that increasingly ship MCP servers. With an MCP client, one generic integration point replaces many bespoke connectors. That fits the "modules = plugins" and "no vendor lock-in" principles. Value is **medium**: it is a force multiplier for power users, but most small-firm users get more from the built-in tools working well. The risk is high if done carelessly, because third-party tool descriptions and outputs are an injection channel into an assistant that can write BOQ data.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium**, touching `erp_chat` plus a new `mcp_servers` sub-area (or a small `mcp_client` module that depends on `oe_erp_chat`).
1. Model `McpServer(tenant_id, name, url, auth_type, encrypted_token, enabled, allowed_tools[], approval_required_tools[], tool_hashes{})`, with a CRUD router and admin-only permissions.
2. Discovery uses the official Python `mcp` SDK `ClientSession` over Streamable HTTP. It calls `tools/list`, namespaces each tool (`mcp__<server>__<tool>`), and caches the list.
3. Registry: `tools.py` becomes a `get_tool_definitions(user, tenant)` that merges internal and allowed MCP tools. Dispatch routes namespaced calls to the MCP session.
4. Safety: `resolve_and_validate_external_url` runs before every connect, with timeouts and the existing result truncation. MCP output is wrapped as untrusted data in the prompt. Tool-definition hashes are pinned, and a definition change disables the tool until re-review (guards against "rug pulls"). Write-capable tools need explicit user confirmation over SSE (an approval event), consistent with "AI proposes, human confirms".
5. Auth: phase 1 supports static bearer tokens. Phase 2 adds an OAuth 2.1 + PKCE client flow with RFC 9728 discovery and an RFC 8707 `resource` parameter. Tokens are never passed through to other servers.
6. Option: for Anthropic/OpenAI, the provider-hosted MCP connectors (`mcp_servers` / `tools: [{type: "mcp"}]`) offload transport. They bypass local SSRF/approval control, though, and do not work for other providers, so a local client should be the default.
7. Audit: log each MCP call via `core/audit.py`. Stdio servers are disabled by default (self-host opt-in only, run in a container).

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- `mcp` Python SDK (MIT, v2.x, Python >=3.10; stdio/Streamable HTTP/SSE): https://pypi.org/project/mcp/
- MCP authorization spec (OAuth 2.1, RFC 9728, RFC 8707): https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization (newer revision 2026-07-28 also published)
- Anthropic MCP connector (beta header; remote HTTP only, tools only; allow/deny list via `tool_configuration`; standard API pricing): https://platform.claude.com/docs/en/agents-and-tools/mcp-connector
- OpenAI Responses API remote MCP (`allowed_tools`, `require_approval`): https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- OWASP MCP Security Cheat Sheet (tool poisoning, confused deputy, pinning): https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html
- Note: `modelcontextprotocol.io` and `docs.anthropic.com` could not be fetched directly from this research environment. The details above for them come from search results and should be re-checked against the live pages.

## Priority: 3/5 — a generic, standards-based extension point with strong long-term leverage, but it needs careful sandboxing and should follow core chat tools and native integrations.

## Sources
- https://pypi.org/project/mcp/
- https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- https://platform.claude.com/docs/en/agents-and-tools/mcp-connector
- https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- https://cheatsheetseries.owasp.org/cheatsheets/MCP_Security_Cheat_Sheet.html
- https://workos.com/blog/mcp-security-risks-best-practices
