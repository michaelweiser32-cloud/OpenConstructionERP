# 072. Filesystem MCP server usage for this ERP

## What it does
The reference Filesystem MCP server (`@modelcontextprotocol/server-filesystem`) lets an MCP client such as Claude Desktop, Claude Code or another LLM host read, search, write, move and edit files, but only inside directories named on the command line. Its tools are `read_text_file`, `read_multiple_files`, `list_directory`, `directory_tree`, `search_files` (matches file names, not contents), `get_file_info`, `write_file`, `edit_file` (with `dryRun`), `create_directory`, `move_file` and `copy_file`. Flags include `--read-only`, `--read-only-dir` and `--confine-roots`.

Small estimating firms keep most of their work in folders on a laptop or NAS: tender packages, drawing PDFs, supplier quote spreadsheets, old estimates. A filesystem MCP server would let an AI assistant work across those folders and the ERP together. Two example tasks: "find every supplier quote PDF for project X and attach it to the RFQ", or "bulk-import the BOQ spreadsheets in /tenders/2026".

It does not connect anything to the ERP. It gives a local AI client access to files. The ERP gains from this only if it also exposes its own MCP server, so the same client can move data between the two.

## Already in the codebase (with file paths)
- No MCP server or client code exists. A search for `mcp` across `backend/app` finds nothing.
- `backend/app/core/storage.py` has a `StorageBackend` abstraction with Local and S3 backends. Local blobs live in `<repo>/data/`.
- `backend/app/modules/erp_chat/tools.py` holds about 17 LLM tool definitions, such as `search_documents`, `get_boq_items`, `create_boq_item` and `run_validation`. They are tool schemas in function-calling format and can be reused almost unchanged as MCP tools.
- `backend/app/modules/documents/`, `backend/app/modules/cde/` and `backend/app/modules/backup/` handle uploads, ISO 19650 CDE states and export/backup.
- `backend/app/core/upload_guards.py` and `backend/app/core/file_signature.py` check uploads, so any file arriving through MCP should go through them.

## Who it helps and how much
- **Estimators on 1–10 person teams who already use Claude Desktop or Claude Code.** Medium value. They can sort and bulk-import local tender folders without writing scripts.
- **Self-hosters and admins.** Low to medium value. A read-only filesystem MCP pointed at `data/` or at backup exports helps with inspection and troubleshooting.
- **Most users get little from it on its own.** It runs on the user's machine (Node.js 24+), and setting it up is a developer task. The real value comes from pairing it with an "ERP as MCP server" feature, so the assistant can push files it finds into the ERP through validated API calls rather than writing into storage directly.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Small** for documentation and configuration only. **Medium** if paired with an ERP MCP server.
1. **Docs only (S):** add a `docs/integrations/mcp-filesystem.md` guide with a sample client config. Point it at a tenders folder with `--read-only-dir`, and recommend a Docker `ro` mount.
2. **ERP MCP endpoint (M):** add a new `mcp_server` module (manifest, router) that mounts a Streamable HTTP MCP endpoint with the official Python SDK or `fastapi-mcp`. It reuses the tool schemas in `erp_chat/tools.py` and the existing JWT/API-key auth and RBAC from `core/permissions.py`. Add one `import_document(project_id, filename, base64)` tool that routes through `documents.service`, upload guards and the validation pipeline, keeping the "AI suggests, human confirms" rule: writes are created as drafts or pending.
3. Do not let the backend talk to the filesystem MCP. The backend already has direct storage access, and adding that hop only enlarges the attack surface.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- Filesystem MCP server, MIT, free: https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem
- MCP Python SDK (stdio, Streamable HTTP, SSE; Python 3.11+), MIT: https://github.com/modelcontextprotocol/python-sdk
- `fastapi-mcp`, which exposes FastAPI endpoints as MCP tools, filters them by tag or operation ID, and reuses FastAPI auth dependencies. MIT according to its repository: https://github.com/tadata-org/fastapi_mcp
- Security caveats from the reference server's README:
  - Access checks are path-based, so hard links and Windows junction races are a risk.
  - Writes are not crash-atomic.
  - Binding the HTTP transport to `0.0.0.0` exposes it to other machines.

  Recommend OS-level read-only mounts.

## Priority: 2/5 — useful mainly as documented setup plus a later ERP-side MCP server, not as a feature of its own
Using the filesystem server needs no ERP code. The investment worth making is an ERP MCP endpoint built on the existing `erp_chat` tools, which then makes the filesystem server useful for bulk-importing local files.

## Sources
- https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem
- https://github.com/modelcontextprotocol/python-sdk
- https://github.com/tadata-org/fastapi_mcp
- https://modelcontextprotocol.io
