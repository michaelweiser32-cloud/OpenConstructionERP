# MCP Server module (`oe_mcp_server`)

Lets external AI clients (Claude, IDE agents, any Model Context Protocol
client) work with your OpenConstructionERP data through the tools the built-in
ERP chat already uses.

| | |
|---|---|
| Endpoint | `POST /mcp` (Streamable HTTP, stateless, JSON responses) |
| Auth | A user API key: `Authorization: Bearer oe_...` or `X-API-Key: oe_...` |
| Status API | `GET /api/v1/mcp_server/info/` (signed-in users; lists the tools you may call) |
| SDK | Official [`mcp` Python SDK](https://github.com/modelcontextprotocol/python-sdk), 1.x |

## Connecting a client

1. Create an API key under **Settings -> API keys**. The key acts as you: it
   sees only what your user may see.
2. Point the client at `https://<your-host>/mcp` with the key as a bearer token.
   Example client configuration:

```json
{
  "mcpServers": {
    "openconstructionerp": {
      "type": "http",
      "url": "https://erp.example.com/mcp",
      "headers": { "Authorization": "Bearer ${OPENCONSTRUCTIONERP_API_KEY}" }
    }
  }
}
```

Keep the key in an environment variable or secret store, never in a committed file.

## Tools

| Tool | Permission | Changes data |
|---|---|---|
| `get_all_projects` | `projects.read` | no |
| `get_project_summary` | `projects.read` | no |
| `compare_projects` | `projects.read` | no |
| `get_boq_items` | `boq.read` | no |
| `get_schedule` | `schedule.read` | no |
| `get_validation_results` | `validation.read` | no |
| `run_validation` | `validation.read` | no (returns the latest reports) |
| `get_risk_register` | `risk.read` | no |
| `get_cost_model` | `costmodel.read` | no |
| `search_cwicr_database` | `costs.read` | no |
| `create_boq_item` | `boq.create` | **yes** |

Resources: `erp://projects`, `erp://projects/{project_id}`,
`erp://projects/{project_id}/boq`, `erp://projects/{project_id}/validation`.

Not exposed yet: the six semantic-search chat tools (`search_boq_positions`,
`search_documents`, `search_tasks`, `search_risks`, `search_bim_elements`,
`search_anything`). They do not enforce per-project access, so they stay off
until that is added.

## Security model

- **Authentication.** Every request needs a valid, unexpired, active API key
  of an active user. Role and permissions are read from the database on every
  request.
- **RBAC.** Each tool maps to an existing permission. Tools you may not call
  are hidden from `tools/list` and refused on `tools/call`. An API key with
  its own `permissions` list is narrowed to that list and loses the admin
  bypass. Project-level access is enforced by the tool handlers.
- **Fail closed.** A chat tool is exposed only if it has an entry in
  `registry.TOOL_POLICY`. New chat tools are never published automatically.
- **AI proposes, human confirms.** A tool that changes data returns a
  *proposal* and saves nothing unless called with `confirm: true` (a real
  boolean). The client is instructed to show the proposal to the user first.
- **Audit.** Every tool call and resource read, including refused ones, is
  written to the audit log (`action = mcp_tool_call`). A confirmed write and
  its audit entry commit in one transaction; if the audit entry cannot be
  written the change is rolled back.
- **Rate limit.** 120 tool calls per minute per API key.
- **Kill switch.** Disable the module under **Modules**; `/mcp` then answers 404.

## Adding tools from another module

```python
from app.core.hooks import hooks
from app.modules.mcp_server.registry import McpToolSpec


@hooks.filter("mcp.tools", module="oe_tendering")
async def add_tools(specs: list[McpToolSpec]) -> list[McpToolSpec]:
    return [
        *specs,
        McpToolSpec(
            name="list_tenders",
            description="List tender packages for a project.",
            input_schema={
                "type": "object",
                "properties": {"project_id": {"type": "string"}},
                "required": ["project_id"],
            },
            permission="tendering.read",
            handler=handle_list_tenders,  # async (session, args, user_id) -> {renderer, data, summary}
            write=False,
        ),
    ]
```

A spec without a permission or handler is dropped. Write tools (`write=True`)
get the `confirm` gate automatically; give them a `preview` function that runs
the same access checks and describes the change. A hook cannot replace a core tool.

## Not in this version

- OAuth 2.1 sign-in for remote connectors (API keys only for now).
- A stdio entry point for local desktop clients.
