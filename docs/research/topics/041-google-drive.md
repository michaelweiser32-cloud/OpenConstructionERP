# 041. Google Drive connector for drawings and documents

## What it does
Lets a user link a Google Drive account (or a Shared Drive) to a project. They can then:
- **Pick and import** drawings (PDF, DWG, IFC, RVT), specs and subcontractor quotes from Drive into `documents` / `cde`, then pass them into takeoff, dwg_takeoff or the CAD conversion pipeline. The usual validation step still runs.
- **Link instead of copy** (optional): store a Drive file reference plus its revision ID, so the ERP shows when the Drive copy has changed ("new revision available"). It does not sync silently.
- **Export** estimates, BOQ Excel/GAEB files, reports and transmittals back to a project folder in Drive.

## Already in the codebase (with file paths)
- There is no Drive connector. The only mention is a help hint telling users to export Excel and import it into Drive by hand: `frontend/src/features/integrations/IntegrationsPage.tsx` (line ~395).
- The integrations module covers messaging only (Slack, Teams, Telegram, Discord, WhatsApp, email, webhook). See `backend/app/modules/integrations/models.py` (`IntegrationConfig.integration_type`) and `backend/app/modules/integrations/service.py`.
- Blob storage abstraction: `backend/app/core/storage.py` (`StorageBackend`, `LocalStorageBackend`, `S3StorageBackend`). Drive should **not** become a storage backend. It is an external source and target.
- Document targets: `backend/app/modules/documents/` and `backend/app/modules/cde/` (revisions and suitability). Token encryption helper: `backend/app/core/crypto.py`. Some OAuth handling exists in `backend/app/modules/opencde_api/` and in the Teams integration.

## Who it helps and how much
Many small contractors and estimators already keep drawings and bid packages in Google Drive (the free tier, or Workspace Business Starter). Today they download each file and upload it again. A connector removes that step for every tender package and keeps drawing revisions traceable. **Value: High for small firms that use Google Workspace.** Firms on Microsoft 365 need SharePoint/OneDrive instead, which is a separate topic. The value is in convenience and fewer stale-revision mistakes, not in a new capability.

## Implementation effort
**Medium.** Touches `integrations` (new `google_drive` type, OAuth config), `documents`/`cde` (import, link, export actions) and a small frontend picker component.
- **Auth:** OAuth 2.0 with the per-file **`drive.file`** scope plus the **Google Picker**. Google recommends this combination. It avoids restricted-scope verification and the third-party security assessment that broad `drive`/`drive.readonly` scopes require. Refresh tokens are encrypted with `core/crypto.py`. Self-hosters register their own Google Cloud OAuth client, so no central app verification is needed.
- **Import:** `files.get?alt=media` streams the file into `StorageBackend.put()`. The service creates a Document/CDE revision that records the Drive `fileId` and `headRevisionId`, and publishes an event such as `documents.imported` so takeoff, CAD and validation pick it up.
- **Change detection:** Poll `changes.list` on a schedule, or use `changes.watch` push channels. Channels expire and must be renewed, so polling is simpler for self-hosted installs behind NAT.
- **Export:** a hook on report/BOQ export that also uploads to a chosen Drive folder.
- **AI angle:** `erp_chat/tools.py` could expose "import from Drive" through the same service, with a human confirming each step.
- Needs one new dependency, `google-api-python-client` (or plain `httpx` against the REST API, keeping it lightweight). The connector should ship as an optional plugin module.

## Building blocks
- Google Drive API v3: free for standard use, with per-minute quota-unit limits. Google's limits page says overage billing is planned for later in 2026, so check it before relying on the free status. https://developers.google.com/workspace/drive/api/guides/limits
- Scope guidance (`drive.file` + Picker): https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- Push notifications (`files.watch` / `changes.watch`): https://developers.google.com/drive/push
- `google-api-python-client` (Apache-2.0): https://github.com/googleapis/google-api-python-client
- **MCP:** Google has an official hosted Drive MCP server (`drivemcp.googleapis.com`). It appears to be in a Developer Preview that requires sign-up; I confirmed this only from search snippets, because the page could not be fetched. https://developers.google.com/workspace/drive/api/reference/mcp. The original reference server `@modelcontextprotocol/server-gdrive` (MIT, search and read only) was archived in May 2025: https://github.com/modelcontextprotocol/servers-archived/tree/main/src/gdrive. Community forks exist (for example https://github.com/piotr-agier/google-drive-mcp) but are unvetted. MCP is good for ad-hoc AI lookups, but the core import/export path should use the REST API directly so it is deterministic.

## Priority: 4/5 — removes daily friction for the many small firms that use Drive, needs only the low-friction drive.file scope, and is medium effort.

## Sources
- https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- https://workspace.google.com/blog/product-announcements/enhancing-security-controls-for-google-drive-third-party-apps
- https://developers.google.com/workspace/drive/api/guides/limits
- https://developers.google.com/drive/push
- https://nango.dev/docs/api-integrations/google-drive/webhooks
- https://developers.google.com/workspace/drive/api/reference/mcp
- https://github.com/modelcontextprotocol/servers-archived/tree/main/src/gdrive
- https://github.com/googleapis/google-api-python-client
- https://github.com/piotr-agier/google-drive-mcp
