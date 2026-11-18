"""MCP server module manifest."""

from app.core.module_loader import ModuleManifest

manifest = ModuleManifest(
    name="oe_mcp_server",
    version="0.1.0",
    display_name="MCP Server",
    description=(
        "Exposes ERP tools (projects, BOQ, costs, schedule, validation) to external "
        "AI clients over the Model Context Protocol at /mcp"
    ),
    author="OpenEstimate Core Team",
    category="integration",
    depends=["oe_users", "oe_projects", "oe_erp_chat"],
    auto_install=True,
    enabled=True,
)
