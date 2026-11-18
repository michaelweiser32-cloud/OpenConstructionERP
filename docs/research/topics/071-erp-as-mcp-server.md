# 071. OpenConstructionERP as an MCP Server

## What it does
The ERP would act as a Model Context Protocol (MCP) server, so any MCP client (Claude Desktop/Code, IDE agents, other LLM hosts) can work with projects, BOQs, cost databases and validation results directly. It would offer:
- **Tools**: actions such as `search_cost_items`, `get_boq`, `add_boq_position`, `run_validation` and `compare_projects`.
- **Resources**: read-only context addressed by URI, e.g. `oe://projects/{id}`, `oe://boq/{id}`, `oe://validation/{report_id}`.
- **Prompts**: canned workflows such as "price this BOQ section" and "explain validation errors".

The ERP becomes the system of record that a user's own AI assistant can query and update. The built-in chat stops being the only way in.

## Already in the codebase (with file paths)
- `backend/app/modules/erp_chat/tools.py` has 17 tools already defined as JSON Schema in Anthropic function-calling format (`TOOL_DEFINITIONS`). A dispatch map (`TOOL_HANDLER_MAP`) connects them to async handlers. The tools include `get_all_projects`, `get_boq_items`, `search_cwicr_database`, `get_cost_model`, `run_validation`, `create_boq_item` and `search_anything`. Project-access checks are in `_require_project_access`. This is about 80% of an MCP tool layer already.
- `backend/app/modules/users/models.py` has `APIKey`, with hashed keys, expiry, `last_used_at` and per-key `permissions`. These can work as bearer credentials for headless MCP clients.
- `backend/app/core/permissions.py` (RBAC) and `backend/app/core/audit` can gate and log tool calls.
- There is no MCP server, no `mcp`/`fastmcp` dependency, and no `/mcp` endpoint anywhere in `backend/app`. This is the gap.

## Who it helps and how much
- **Small estimating firms (1-10 people)** already pay for a general AI assistant. They gain the most: "find the CWICR rate for C30/37 walls and add 40 m3 to BOQ 2" works from the tool they already use, with no extra per-seat AI cost in the ERP.
- **Power users and integrators** can script estimating workflows with agents, without learning the REST API.
- **The project's positioning** gains too: an open-source ERP that ships with an MCP server sets it apart. As of this research, the only Procore MCP servers found are community-built (e.g. TylerIlunga/procore-mcp-server, MIT) or hosted by third parties (Truto, CData). No official vendor server was found for Procore or Autodesk.
- Value: High. AI calls stay human-confirmed if write tools return drafts or require confirmation, which matches the "AI-augmented, human-confirmed" principle.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Small-to-Medium.** Create a new module `backend/app/modules/mcp_server/` with `manifest.py` (`depends=["oe_erp_chat", "oe_users"]`):
1. Build a FastMCP / `mcp` SDK server and register every entry of `TOOL_DEFINITIONS` as a tool, wrapping the matching `TOOL_HANDLER_MAP` handler. This is a thin adapter, so nothing is duplicated.
2. Add resources for projects, BOQs and validation reports, using the existing services and repositories.
3. Mount the server with `mcp.http_app(path="/mcp")` on the FastAPI app and combine lifespans. Use the Streamable HTTP transport. Optionally add a stdio entry point (`python -m app.modules.mcp_server`) for local Desktop use.
4. Auth, phase A: bearer API key mapped to a user, then RBAC. Phase B: OAuth 2.1 per the MCP authorization spec, so remote connectors can sign users in.
5. Hook in more tools: let other modules register tools through `core/hooks.py` (filter `mcp.tools`), so plugins (tendering, schedule) add tools automatically.
6. Write tools: return proposals, or require an explicit `confirm=true`; emit audit events; apply rate limits.
7. Write tests with an in-memory MCP client.

Avoid auto-mirroring the whole OpenAPI surface. The FastMCP docs say curated tools work much better with LLMs than a mirrored API.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **MCP Python SDK** (official), MIT; supports stdio, Streamable HTTP and SSE: https://github.com/modelcontextprotocol/python-sdk
- **FastMCP**, Apache-2.0; has `FastMCP.from_fastapi`, `http_app()` mounting and `combine_lifespans`: https://github.com/jlowin/fastmcp
- **fastapi_mcp** (Tadata), MIT; exposes FastAPI endpoints as MCP tools, with auth through `Depends()`, ASGI transport and `/mcp` mount: https://github.com/tadata-org/fastapi_mcp
- **MCP specification**, including OAuth 2.1-based authorization for HTTP transports: https://github.com/modelcontextprotocol/modelcontextprotocol. The modelcontextprotocol.io site could not be fetched from this session, so spec details were not re-verified here.
- Reference only, not a dependency: the community Procore MCP server (MIT) shows demand in construction: https://github.com/TylerIlunga/procore-mcp-server

## Priority: 5/5 — The tool layer already exists in erp_chat, so a thin, well-understood adapter turns the ERP into an AI-native back end for any assistant.

## Sources
- https://github.com/modelcontextprotocol/python-sdk
- https://github.com/jlowin/fastmcp
- https://raw.githubusercontent.com/jlowin/fastmcp/main/docs/integrations/fastapi.mdx
- https://github.com/tadata-org/fastapi_mcp
- https://github.com/modelcontextprotocol/modelcontextprotocol
- https://github.com/TylerIlunga/procore-mcp-server
- https://truto.one/blog/connect-procore-to-claude-control-daily-logs-crews-and-project-webhooks/
- https://www.cdata.com/kb/tech/procore-mcp-claude-code.rst
