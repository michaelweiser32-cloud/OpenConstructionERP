# 074. Database MCP servers (Postgres/SQLite) for read-only analytics on ERP data

## What it does
A database MCP (Model Context Protocol) server lets an AI client such as Claude Desktop, Cursor or a local LLM agent look at the ERP schema and run SQL against it. The user can ask things like "which projects overran their BOQ budget by more than 10% this quarter?" or "list open RFIs older than 14 days by project" and get the answer without writing SQL. For an ERP, the server must be **read-only and scoped to what the user is allowed to see**. Without that, an LLM with database access is a data-loss and data-leak risk.

## Already in the codebase (with file paths)
- No MCP server or MCP endpoint exists. A grep for `mcp` in `backend/app` and `frontend/src` finds nothing.
- `backend/app/modules/erp_chat/tools.py` has about 17 curated LLM tools, mostly read-only: `get_all_projects`, `get_boq_items`, `get_schedule`, `compare_projects`, `search_anything` and others. Access goes through `_require_project_access`, which checks for project owner or admin. There is no free-form SQL tool. One tool writes data (`create_boq_item`).
- `backend/app/config.py` defaults to SQLite (`sqlite+aiosqlite:///./openestimate.db`) and uses PostgreSQL through `DATABASE_URL` in production. Any MCP option therefore has to cover both.
- The frontend has a "Data Explorer" pivot view (`frontend/src/app/App.tsx`, see `docs/gifs/13_Data_Explorer_Pivot.gif`). It is built-in analytics, but it does not use natural language or any external tool.

**Gap:** there are two missing pieces. (a) There is no supported, documented way to point an external MCP database server at an OpenConstructionERP database safely. (b) There is no first-party MCP endpoint that would expose the existing `erp_chat` tools with project-level permissions.

## Who it helps and how much
- **Owner or estimator at a small firm (1-20 staff):** gets ad-hoc reporting ("margin by trade", "supplier spend YTD") without a BI tool or SQL skills. The value is medium to high, but it depends on the user already using an MCP-capable client.
- **Integrator or power user:** gets fast schema exploration and query tuning, for example with the index and health tools in Postgres MCP Pro.
- **Limits:** raw SQL ignores the app's project-level permissions. It suits a single-tenant owner or admin, not a shared multi-user deployment.

## Implementation effort
**Small** for documentation plus a hardened setup. **Medium** for a first-party MCP endpoint.
1. **Small (docs + SQL, no core change):** ship a `deploy/mcp/` guide and a migration that creates a `oe_readonly` Postgres role. The role gets `SELECT` only on non-sensitive tables, explicitly excludes auth tokens, API keys, password hashes and audit secrets, and sets `default_transaction_read_only=on` and `statement_timeout`. Expose curated `analytics_*` SQL views (BOQ totals, EVM, open RFIs/punch items) so the LLM gets a stable, documented schema. For SQLite, open the file in read-only mode (`mode=ro` URI) or work on a nightly copy made by the `backup` module.
2. **Medium (new module `mcp_server`):** add a manifest-based module that serves the MCP Streamable HTTP transport. It would reuse the `erp_chat/tools.py` tool registry with JWT/API-key auth, so `_require_project_access` still applies. An optional `run_readonly_sql` tool would run only against the `analytics_*` views, with parsing, a row limit and a timeout. Each call would be logged through `core/audit`. Tools that write stay disabled unless confirmed, in line with the "AI-augmented, human-confirmed" principle.

## Building blocks
- **Postgres MCP Pro**: MIT license, Python. `--access-mode=restricted` runs SQL in read-only transactions, uses pglast to reject COMMIT/ROLLBACK, and limits execution time. https://github.com/crystaldba/postgres-mcp
- **DBHub** (Bytebase): MIT license (per directory listings). Supports Postgres, MySQL, SQL Server and SQLite, with `--readonly` and `--max-rows`. https://github.com/bytebase/dbhub
- **MCP Toolbox for Databases** (Google, formerly genai-toolbox): Apache-2.0. Tools are defined declaratively in YAML, which fits "curated queries only". Postgres support is confirmed. SQLite support is not verified in the official README. https://github.com/googleapis/genai-toolbox
- **The reference `postgres`/`sqlite` servers are archived** (May 2025) and come with "NO SECURITY GUARANTEES". A public write-up describes a read-only bypass in the Postgres server through multi-statement `COMMIT` (no CVE). **Do not recommend them.** https://github.com/modelcontextprotocol/servers-archived
- Community SQLite read-only servers exist, for example StacklokLabs/sqlite-mcp (Go, read-only flag). Their maintenance and licenses are not verified here, so evaluate each one before recommending it.
- **Official MCP Python SDK** (MIT), for building the first-party endpoint inside FastAPI. https://github.com/modelcontextprotocol/python-sdk

## Priority: 3/5
Cheap to enable and high-leverage for owner-operators, but raw SQL access bypasses project permissions. Ship hardened docs, a read-only role and analytics views now, and build a permission-aware first-party MCP module later.

## Sources
- https://github.com/crystaldba/postgres-mcp
- https://github.com/bytebase/dbhub
- https://github.com/googleapis/genai-toolbox
- https://github.com/modelcontextprotocol/servers-archived
- https://dev.to/grove_chatforest/the-postgresql-mcp-server-read-only-protection-that-wasnt-2m88
- https://github.com/stackloklabs/sqlite-mcp
- https://github.com/modelcontextprotocol/python-sdk
- https://www.postgresql.org/docs/current/runtime-config-client.html
