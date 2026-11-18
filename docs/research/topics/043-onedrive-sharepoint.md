# 043. OneDrive / SharePoint connector via Microsoft Graph

## What it does
Links OpenConstructionERP projects to folders in OneDrive for Business or SharePoint document libraries through Microsoft Graph. The connector would:
- **Import / pick:** browse a linked library and pull drawings, specs, tender PDFs and Excel BOQs into `documents`/`cde`/`takeoff` without downloading and re-uploading them by hand.
- **Watch for changes:** a Graph change-notification subscription on the drive acts as a signal, then a `driveItem: delta` call fetches what changed. New drawing revisions show up as new document versions and go through the normal validation pipeline.
- **Export / publish:** push generated reports, GAEB/Excel BOQs and transmittal packages back into a client's or the team's SharePoint folder, using resumable upload sessions for large files.
- Optionally, act as a `StorageBackend`, so a small firm's existing M365 tenant holds the files.

## Already in the codebase (with file paths)
- `backend/app/core/storage.py` defines a `StorageBackend` ABC with `LocalStorageBackend` and `S3StorageBackend`, chosen by `STORAGE_BACKEND`. There is no Graph backend.
- `backend/app/modules/integrations/teams.py` sends Teams notifications through incoming webhooks only. It has no OAuth and no Graph client.
- `backend/app/modules/documents/` and `backend/app/modules/cde/` handle uploads, versions and suitability states. Both take local uploads only.
- A grep for `onedrive`, `sharepoint` and `graph.microsoft` in `backend/app` and `frontend/src` returns nothing. There is also no Google Drive or Dropbox connector.
- **Gap:** there is no Microsoft Entra ID OAuth flow, token storage, drive picker, sync job or webhook receiver.

## Who it helps and how much
Many small contractors and estimators already pay for Microsoft 365 Business, so their drawings and spec folders sit in SharePoint or OneDrive. This connector removes the "download from SharePoint, upload to ERP" step for every drawing revision. It also keeps one source of truth, which matters when clients or architects share SharePoint links. The value is high for M365 shops and zero for Google Workspace shops, so this connector pairs naturally with a Google Drive one.

## Implementation effort
**Medium.** Read/import plus export is about 2–3 weeks. Two-way change sync and a storage backend take longer.
- New module `backend/app/modules/ms_graph/` (`oe_ms_graph`, depends on `oe_documents` and `oe_cde`). It contains:
  - `manifest.py`.
  - `models.py`: a tenant connection with encrypted refresh token, plus `DriveLink`, which maps project ↔ drive id/folder id and stores the delta token.
  - `router.py`: OAuth callback, folder browse, link/unlink, and a webhook endpoint that echoes `validationToken`.
  - `service.py`: delta sync, import into `documents` as new versions, and upload sessions for export.
- Auth uses the authorization-code flow against Entra ID with delegated scopes (`Files.Read.All`/`Files.ReadWrite.All`, or `Sites.Selected` for least privilege).
- Sync:
  - Subscribe to `/drives/{id}/root`.
  - Renew before expiry. Microsoft's guidance gives roughly 30 days for driveItem subscriptions, so renewal is a scheduled job.
  - Run delta right after subscribing, plus a periodic delta poll as a backstop for lost notifications. Microsoft's scan guidance recommends both.
- Events: publish `documents.imported_from_graph`, which existing validation and notification hooks can consume.
- Frontend: a "Connect Microsoft 365" card in integrations settings and a folder picker in the project documents tab, using i18n strings throughout.
- Validation rules: file-type allowlist, size checks, and duplicate detection by Graph `eTag`/`cTag`.
- Optional later step: `GraphStorageBackend(StorageBackend)` in `core/storage.py`.

## Building blocks
- **Microsoft Graph REST v1.0:**
  - driveItem delta, subscriptions and createUploadSession.
  - Graph is available with an M365 subscription and has no separate per-call fee for these file APIs. Throttling limits apply.
  - Docs: https://learn.microsoft.com/graph/api/driveitem-delta
- **msgraph-sdk (Python)** by Microsoft: MIT licence, async by default, Python 3.10+. https://github.com/microsoftgraph/msgraph-sdk-python
  - A lighter alternative fits the "lightweight" principle better: plain `httpx`, which the project already uses, plus `msal` (MIT) for tokens.
- **MSAL for Python** (MIT) for OAuth token acquisition and refresh: https://github.com/AzureAD/microsoft-authentication-library-for-python
- **Softeria ms-365-mcp-server:**
  - Community project, not Microsoft. MIT licence, about 1.1k stars.
  - Has OneDrive and SharePoint tools, supports `Sites.Selected`, and offers device-code, OAuth and app modes.
  - Could give `erp_chat`/AI agents ad-hoc file access instead of building custom tools.
  - https://github.com/Softeria/ms-365-mcp-server
- **Official Microsoft MCP servers:** third-party directories mention a SharePoint Embedded MCP server and an Agent365 OneDrive/SharePoint remote server. I could not confirm their status or availability from Microsoft's own pages, so treat them as unverified.

## Priority: 4/5 — many small firms already keep project files in M365, and this connector removes the manual re-upload step for every drawing revision; it is Medium effort because the official APIs are well documented
## Sources
- https://learn.microsoft.com/graph/api/driveitem-delta
- https://learn.microsoft.com/onedrive/developer/rest-api/concepts/scan-guidance
- https://learn.microsoft.com/graph/api/driveitem-createuploadsession
- https://learn.microsoft.com/en-us/graph/api/resources/uploadsession
- https://pnp.github.io/blog/post/microsoft-graph-webhook-delta-query/
- https://github.com/microsoftgraph/msgraph-sdk-python
- https://github.com/AzureAD/microsoft-authentication-library-for-python
- https://github.com/Softeria/ms-365-mcp-server
