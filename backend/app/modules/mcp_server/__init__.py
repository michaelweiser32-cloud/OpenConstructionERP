"""MCP server module.

Wraps the existing ``erp_chat`` tool handlers and exposes them to any
Model Context Protocol client at ``/mcp`` (Streamable HTTP).

Security model:
    * Every request authenticates with a per-user API key.
    * Every tool maps to an existing RBAC permission (fail closed).
    * Write tools return a proposal unless called with ``confirm=true``.
    * Every tool call is written to the audit log.
"""
