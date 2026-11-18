# 096. Backup, export and data portability (full project export, S3 backups, restore)

## What it does
Lets a firm (a) download one complete, self-describing archive of a single project or the whole tenant (database rows plus attached files such as drawings, photos and PDFs), (b) run scheduled, encrypted, off-site backups to any S3-compatible bucket with retention, and (c) restore either a whole instance or one project into another instance. This is the "no vendor lock-in" promise in practical form: a small business can leave, move servers, or recover from a dead VPS without a consultant.

## Already in the codebase (with file paths)
- `backend/app/modules/backup/router.py`: `POST /export/`, `/restore/`, `/validate/`. Builds an in-memory ZIP with `manifest.json` and one JSON file per table, plus a SHA checksum and format version `1.0.0`. Restore inserts in FK order; `backup.admin` permission required.
- Gaps found there: hard-coded registry of only ~19 tables (`_BACKUP_TABLE_DEFS`: users, projects, BOQ, schedule, costmodel, risk, change orders, documents metadata, assemblies, tendering, AI settings). RFI, submittals, punchlist, field reports, inspections, finance, procurement, contacts, markups, takeoff, CDE and others are not included. File blobs are not included (only the `documents` rows). Rows are scoped by `created_by`/`owner_id`, so projects shared by teammates may be missing. There is no per-project export, no scheduling, no encryption, no streaming (100 MB upload cap, built in RAM).
- `backend/app/core/storage.py`: `StorageBackend` with `LocalStorageBackend` and `S3StorageBackend` (optional `aioboto3`, presigned URLs). This is reusable as a backup destination.
- `frontend/src/features/settings/BackupRestore.tsx`: settings UI for manual export/restore.
- Many module routers already export CSV/Excel/GAEB (`boq`, `costs`, `schedule`, `finance`, `rfi`, ...), which covers format-level portability but not a single complete archive.

## Who it helps and how much
High for small firms on a single VPS or laptop install: they have no DBA, and a lost disk means lost bids. Scheduled off-site backups are the cheapest form of insurance. A per-project archive also helps with handover to a client or JV partner, archiving closed jobs (many jurisdictions require multi-year retention of project records), and moving between self-hosted and hosted deployments. It is also a trust signal when choosing an open-source ERP.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch)
**Medium**, in `backup` plus small hooks in `core`.
1. Replace the static table list with a registry: each module manifest declares its exportable models (and project FK column). The module loader collects them, so new modules are covered automatically.
2. Archive format v2: streaming ZIP (`manifest.json`, `tables/*.jsonl`, `files/<storage key>`), with file blobs streamed from `StorageBackend`. Project scope = all rows whose `project_id` matches, plus the referenced cost items and assemblies. Use ID remapping on import so a project can be cloned into another instance.
3. Scheduled job (in-process scheduler for dev, Celery beat when Redis is present) writes archives to a configured S3 bucket via `S3StorageBackend`, with optional encryption and a retention count.
4. Restore runs the validation pipeline before commit (schema version, checksums, FK integrity), with a dry-run report shown in the UI.
5. For whole-instance disaster recovery, document and ship a `pg_dump` plus restic/rclone sidecar recipe in `deploy/` instead of reimplementing it.

## Building blocks (free/open-source libs, APIs, MCP servers)
- PostgreSQL `pg_dump`/`pg_restore` (PostgreSQL License): https://www.postgresql.org/docs/current/app-pgdump.html
- restic (BSD-2-Clause), encrypted and deduplicated snapshots to S3/B2: https://github.com/restic/restic
- rclone (MIT), sync to more than 70 storage providers: https://github.com/rclone/rclone
- pgBackRest (MIT), PITR to S3/Azure/GCS for larger installs: https://pgbackrest.org/
- Backrest (GPL-3.0), web UI for restic, an option to bundle: https://github.com/garethgeorge/backrest
- aioboto3 (Apache-2.0), already the optional S3 dependency: https://github.com/terrycain/aioboto3
- Storage targets: Backblaze B2 (about $6.95/TB/month, free egress up to 3x stored data): https://www.backblaze.com/cloud-storage/pricing. Cloudflare R2 (10 GB free, $0 egress): https://developers.cloudflare.com/r2/pricing/. MinIO self-hosted (AGPL-3.0).
- MCP: awslabs/mcp ships AWS servers (an S3 Tables server, a general AWS API/AWS MCP server), but I found no official general-purpose S3 object backup MCP server: https://github.com/awslabs/mcp. Better approach: expose `backup.create_export` and `backup.list` as tools in `erp_chat/tools.py`, with human confirmation before any restore.

## Priority: 4/5. Core trust and disaster-recovery feature, half-built today
Half of it exists. Completing table and file coverage, plus scheduled S3 backups, is a medium job that protects every user.

## Sources
- https://github.com/restic/restic
- https://pkg.go.dev/github.com/restic/restic
- https://github.com/rclone/rclone
- https://pgbackrest.org/
- https://github.com/garethgeorge/backrest
- https://www.backblaze.com/cloud-storage/pricing
- https://developers.cloudflare.com/r2/pricing/
- https://github.com/awslabs/mcp
- https://www.postgresql.org/docs/current/app-pgdump.html
