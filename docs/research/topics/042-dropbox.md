# 042. Dropbox connector for drawings/documents

## What it does
Lets a project link one or more Dropbox folders, such as "/Projects/<name>/Drawings", to the ERP. Files in them (PDF plan sets, DWG/RVT/IFC models, specs, photos) then show up in Documents/CDE without anyone uploading them again. The core flows are:
- **Import / pick:** the user picks files with the Dropbox Chooser, or the connector watches a whole folder.
- **Sync:** Dropbox webhooks plus `files/list_folder/continue` cursors pick up new and changed revisions. Each new revision becomes a document version and can feed sheet splitting, takeoff or CAD conversion.
- **Publish back (optional):** generated reports, BOQ exports and transmittals are saved to Dropbox with the Saver or `files/upload`.

## Already in the codebase (with file paths)
- No Dropbox code exists. A grep for "dropbox" over `backend/app` and `frontend/src` finds nothing.
- `backend/app/core/storage.py` defines a `StorageBackend` ABC with `LocalStorageBackend` and `S3StorageBackend`. This is for blob storage, not for syncing a user's cloud folders, but it is where imported bytes would be stored.
- `backend/app/modules/documents/router.py` has `/upload/`, `/photos/upload/`, `/sheets/split-pdf/` and sheet version history. These are the natural places for imported files to land.
- `backend/app/modules/cde/` holds ISO 19650-style containers and suitability codes (`suitability.py`). It could map a Dropbox folder to a WIP area.
- `backend/app/modules/integrations/models.py` has a generic `IntegrationConfig` with `integration_type`, a JSON `config` field and `events`. It also has `WebhookEndpoint`.
- `backend/app/core/crypto.py` has `encrypt_secret` and `decrypt_secret`, which can store OAuth refresh tokens.
- The existing integrations (slack, teams, telegram, whatsapp, discord, email) are outbound notifications only. None of them reads files in.

## Who it helps and how much
**High for small firms.** Many small contractors and estimators already keep their files in consumer or business Dropbox, often shared with architects and subs. A connector removes the download-then-upload step every time a revision arrives, and it keeps the ERP's sheet versions in step with the files people actually share. The benefit is smaller for firms that work on SharePoint or Google Drive, so the design should stay storage-agnostic and let Drive and OneDrive reuse the same abstraction.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** The connector would be a new module, `backend/app/modules/dropbox_connector/` (or a generic `cloud_drives` module with a Dropbox provider), with `manifest.py` declaring `depends=["oe_documents", "oe_integrations"]`. Sketch:
1. **OAuth 2 (PKCE or code flow)** with offline access. Store the encrypted refresh token in `IntegrationConfig.config` with `integration_type="dropbox"`.
2. **Folder link model:** `project_id`, `dropbox_path`, the cursor and `last_synced`.
3. **Webhook endpoint:** `/api/v1/dropbox_connector/webhook` answers the challenge and verifies the `X-Dropbox-Signature` HMAC. It then queues a background job that calls `list_folder/continue` and resets the cursor when Dropbox returns `reset`. Dropbox expects a quick response, so this work must not block the request.
4. **Import pipeline:** download the file, then content-hash dedupe (Dropbox provides `content_hash`), then `StorageBackend.put`, then create a document or sheet version. Then emit an event such as `documents.file_imported` so takeoff and CAD conversion can react.
5. **Validation rules:** flag unsupported file types, unparseable revision numbers in file names and duplicate content.
6. **Frontend:** a "Link Dropbox folder" dialog (Chooser drop-in) under project documents.
7. **Export back:** use `files/upload` for files up to 150 MB per request and upload sessions for larger ones.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Dropbox API v2** (HTTP): free to use with any Dropbox account. Needs an app registered in the App Console. Covers webhooks, `list_folder` cursors and upload sessions. https://www.dropbox.com/developers/reference/webhooks
- **dropbox-sdk-python:** official SDK, MIT license. Supports PKCE and refresh tokens. https://github.com/dropbox/dropbox-sdk-python, https://pypi.org/project/dropbox/
- **Chooser / Saver drop-ins:** hosted JS, free. Needs the app key, which is not secret, plus registered domains. https://www.dropbox.com/developers/dropins
- **Official Dropbox remote MCP server (beta):** `https://mcp.dropbox.com/mcp`, authorized with Dropbox OAuth. I could not confirm whether it can write files or only read them, because third-party write-ups disagree. It is useful for AI chat over Dropbox files, but it does not replace a server-side sync connector. https://help.dropbox.com/integrations/connect-dropbox-mcp-server
- **Dropbox Dash MCP:** a separate product that needs a Dash plan. It does company-wide search, not file sync, so it is not relevant here.

## Priority: 4/5 — Many small firms already exchange drawings through Dropbox; a Medium-effort sync into the existing Documents/CDE removes daily re-upload work, and the abstraction can be reused for Drive and OneDrive.

## Sources
- https://www.dropbox.com/developers/reference/webhooks
- https://www.dropbox.com/developers/webhooks/docs
- https://www.dropbox.com/developers/dropins
- https://github.com/dropbox/dropbox-sdk-python
- https://help.dropbox.com/integrations/connect-dropbox-mcp-server
- https://chatforest.com/reviews/dropbox-mcp-server/
- https://developers.qodex.ai/dropbox-s-public/dropbox-api-reference/files-59/upload_session-start
