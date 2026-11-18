# 098. Autodesk Build / Autodesk Platform Services (ACC) integration

## What it does
Autodesk Platform Services (APS, formerly Forge) is Autodesk's REST API platform. Its Autodesk Construction Cloud (ACC) endpoints expose Autodesk Build/Docs data: hubs and projects, files and folders (Data Management API), Issues, RFIs, Submittals, Cost Management (budgets, contracts, change orders, expenses), Takeoff inventory, and model translation and metadata via the Model Derivative API. A connector would let OpenConstructionERP pull an ACC project's drawings and models, issues, RFIs and takeoff quantities into the local estimate. It could also push BOQ totals into ACC Cost budgets, so an estimator can price in OpenConstructionERP while the GC or owner runs the job in ACC.

## Already in the codebase (with file paths)
- No APS or ACC client exists. A grep for `autodesk|bim360|forge` finds only marketing text ("no Autodesk license required") in `backend/app/core/marketplace.py` and `backend/app/modules/takeoff/router.py`.
- Native RVT/IFC/DWG import already runs through the DDC converter, with no Autodesk dependency: `backend/app/modules/bim_hub/` (models, elements, quantity maps, BOQ linking), `backend/app/modules/boq/cad_import.py`, and `frontend/src/modules/ddc-rvt-converter/manifest.ts`.
- `backend/app/modules/integrations/` holds only webhook-style connectors (Slack, Teams, Telegram, WhatsApp, Discord, email). Per `teams.py`/`discord.py`, they use no OAuth, so there is no reusable OAuth2 token store yet.
- The modules that mirror ACC objects already exist: `rfi`, `submittals`, `punchlist`, `changeorders`, `cde`, `documents`, `costmodel`.

## Who it helps and how much
- **Subcontractors and estimators working for GCs that mandate ACC: high value.** Today they re-key drawings, RFIs and issues by hand. Syncing files and RFIs, and pushing a priced BOQ into ACC Cost budgets, would remove that duplicate entry.
- **Small firms not on ACC: low value.** The ERP already reads RVT/IFC without Autodesk, so APS adds little for them.
- Overall the value is moderate and limited to one segment. It is a strong "plays nicely with the incumbent" feature for interoperability with larger partners.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium-Large.** The effort is Medium for a read-only MVP (hubs, projects, files, issues, RFIs) and Large for two-way Cost and RFI sync.
- New plugin module `backend/app/modules/acc_connector/` (manifest `oe_acc_connector`, `depends=["oe_projects","oe_documents","oe_rfi","oe_boq"]`, `auto_install=False`).
- It needs an OAuth2 3-legged flow (APS app client ID and secret entered by the tenant, never shipped) and an encrypted token table with refresh handling. The token store could be generalised into `integrations` for later connectors.
- `service.py` would map ACC entities to local models: Data Management items to `documents`/`cde`, Issues to `punchlist`, RFIs to `rfi`, and Cost budgets to and from `boq`/`costmodel`. Each row keeps its ACC ID in `metadata` so it is not imported twice.
- A background sync job would run through the existing event bus, with an ACC webhook receiver (APS Webhooks API) for push updates.
- A validation rule set `acc_import`, covering unmapped units, missing cost codes and duplicate external IDs, would run before data is stored. This follows the project rule that validation is mandatory.
- Optionally, `erp_chat/tools.py` could gain read-only ACC tools.
- The APS Free tier has monthly caps on metered APIs, and Model Derivative is token-metered. Translating models should therefore stay with the local DDC pipeline rather than Model Derivative.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **APS / ACC REST APIs:** https://aps.autodesk.com/en/docs/acc/v1/ . A developer account is free. Business model: Free tier with monthly allowances on metered APIs, then Paid (Flex tokens or pay-as-you-go). See https://aps.autodesk.com/pricing . The exact per-API caps for ACC endpoints could not be verified (the page was unreachable from this session), so check them before relying on any figure.
- **ACC Cost Management API** (budgets, contracts, budgets-contracts link, ERP integration tutorial): https://aps.autodesk.com/en/docs/acc/v1/tutorials/cost/integrate-with-external-system . Rate limit is about 500 requests per minute per user.
- **Official sample code for Cost exchange:** https://github.com/autodesk-platform-services/aps-acc-cost-exchange (Autodesk sample repository; check its license before reuse).
- **Official APS MCP server (Node.js):** https://github.com/autodesk-platform-services/aps-mcp-server-nodejs . MIT licensed, uses Secure Service Accounts, and lists ACC projects and issues. It was **archived (read-only) on 7 May 2026**, so treat it as a reference only. No hosted official successor could be verified.
- **Community MCP servers:** examples at https://glama.ai/mcp/servers/n38ot4vlm6 and an unofficial Forma one. They are third-party and unverified, so they are not recommended as dependencies.
- **Python HTTP:** `httpx` (BSD), already a typical FastAPI dependency. No official Autodesk Python SDK is required.

## Priority: 2/5 — valuable only for subs and estimators tied to ACC-mandating GCs; native RVT/IFC import already covers the core need without Autodesk lock-in or metered costs.

## Sources
- https://aps.autodesk.com/en/docs/acc/v1/
- https://aps.autodesk.com/pricing
- https://aps.autodesk.com/node/3776
- https://aps.autodesk.com/en/docs/acc/v1/tutorials/cost/integrate-with-external-system
- https://aps.autodesk.com/en/docs/acc/v1/tutorials/cost/link-budgets-and-contract-new
- https://aps.autodesk.com/en/docs/acc/v1/overview/rate-limits/cost-management-rate-limits
- https://github.com/autodesk-platform-services/aps-acc-cost-exchange
- https://github.com/autodesk-platform-services/aps-mcp-server-nodejs
- https://glama.ai/mcp/servers/n38ot4vlm6
