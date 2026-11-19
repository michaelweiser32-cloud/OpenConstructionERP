# Deploying OpenConstructionERP online (free tier)

This guide puts OpenConstructionERP on the public internet **at zero cost**
and keeps your data safe across restarts:

| Piece | Service | Cost | Card needed |
|---|---|---|---|
| App (backend API + web UI in one container) | **Render** free web service | $0 | No |
| Database (durable) | **Neon** free PostgreSQL | $0 | No |

> OpenConstructionERP is AGPL-3.0 software by DataDrivenConstruction
> (upstream: <https://github.com/datadrivenconstruction/OpenConstructionERP>).
> If you run a modified version for other people over a network, the AGPL
> requires you to offer them the source of your version — the app already
> exposes `/api/source` for this. Keep the license notices intact.

Contents

1. [What you get — and the real free-tier limits](#1-what-you-get--and-the-real-free-tier-limits)
2. [Create the database on Neon](#2-create-the-database-on-neon)
3. [Deploy the app on Render](#3-deploy-the-app-on-render)
4. [First login and day-to-day use](#4-first-login-and-day-to-day-use)
5. [Durable file storage (S3-compatible bucket)](#5-durable-file-storage-s3-compatible-bucket)
6. [Environment variable reference](#6-environment-variable-reference)
7. ["Lite" mode for 512 MB](#7-lite-mode-for-512-mb)
8. [Demo accounts on a public URL](#8-demo-accounts-on-a-public-url)
9. [Upgrade paths (persistent disk, VPS)](#9-upgrade-paths-persistent-disk-vps)
10. [Run it locally / on a VPS with bundled PostgreSQL](#10-run-it-locally--on-a-vps-with-bundled-postgresql)
11. [Existing databases & migrations](#11-existing-databases--migrations)
12. [Security checklist](#12-security-checklist)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. What you get — and the real free-tier limits

**Render free web service** (render.com/docs/free):

- 0.1 CPU, **512 MB RAM**, no credit card.
- **Spins down after 15 minutes without traffic.** The next visitor waits
  roughly **1 minute** while it starts again (Render shows a loading page).
- **The container filesystem is ephemeral**: anything written to local disk
  is **lost on every spin-down, restart and redeploy**. That is why the
  database must live on Neon. Uploaded files are stored on local disk
  unless you configure a bucket — see
  [Known limitation: uploaded files](#known-limitation-uploaded-files).
- 750 free instance-hours per month per workspace (enough for one service
  running all month).
- Render's own free PostgreSQL **expires 30 days after creation** — this
  guide deliberately does **not** use it.

**Neon free plan** (neon.com/pricing):

- $0, no credit card, **1 GB storage per project**, **100 compute-hours
  (CU-hours) per month**, durable storage.
- Compute **scales to zero after 5 minutes idle** and resumes in
  milliseconds on the next query.
- Scale-to-zero pairs well with Render's spin-down: when nobody uses the
  app, both sleep and burn no hours; the first request wakes Render (≈1
  min), whose startup wakes Neon (sub-second).

**What survives what**

| Event | Data in Neon (projects, BOQs, users…) | Files on local disk (`STORAGE_BACKEND=local`) | Files in an S3 bucket (`STORAGE_BACKEND=s3`) |
|---|---|---|---|
| Render spin-down / wake-up | ✅ kept | ❌ lost | ✅ kept |
| Redeploy / restart | ✅ kept | ❌ lost | ✅ kept |
| No `DATABASE_URL` set (SQLite fallback) | ❌ **everything lost** | ❌ lost | ⚠️ files kept, but the database rows pointing at them are lost |

### Known limitation: uploaded files

Projects, BOQs, cost data, schedules, tasks and users are durable in
Neon. **Uploaded files** are durable only with an S3-compatible bucket
([§5](#5-durable-file-storage-s3-compatible-bucket)): with
`STORAGE_BACKEND=s3`, every upload type (documents, photos, PDF sheets,
meeting transcripts, takeoff PDFs, DWG/DXF drawings, punch-list photos and
BIM/CAD models) is stored in the bucket. Without a bucket, uploads are lost
on every restart. The one derived file still on local disk is the BIM
element table used by the BIM "data query" view (see §5).

---

## 2. Create the database on Neon

1. Go to <https://neon.com> → **Sign up** (GitHub or e-mail; no card).
2. **Create project**:
   - *Project name*: e.g. `openconstructionerp`
   - *Postgres version*: 16 (or newer)
   - *Region*: pick the one **closest to your Render region** (e.g. both in
     Frankfurt / EU Central, or both in Oregon / US West). Same-region keeps
     every query fast.
   - Click **Create project**.
3. On the project dashboard click **Connect**.
   - *Branch*: `main`, *Database*: `neondb` (default), *Role*: the default
     owner role.
   - Turn **Connection pooling ON** — this gives the **pooled** connection
     string, whose host contains `-pooler`.
   - Copy the string. It looks like
     `postgresql://<role>:<password>@ep-<name>-pooler.<region>.aws.neon.tech/neondb?sslmode=require&channel_binding=require`
4. Keep it somewhere private (password manager). **Never commit it to git.**

You can paste Neon's string **exactly as shown** — the app rewrites
`sslmode` / `channel_binding` into the right form for its async driver
(asyncpg) and its migration driver (psycopg2), and switches asyncpg into
PgBouncer-safe mode automatically for `-pooler` hosts.

---

## 3. Deploy the app on Render

You need: a GitHub account with this fork, and a Render account
(<https://render.com> → **Get Started** → sign in with GitHub; no card).

### Option A — Blueprint (recommended, pre-filled settings)

1. Render dashboard → **New** → **Blueprint**.
2. Connect your GitHub account if asked, then pick **your fork** of
   OpenConstructionERP.
3. **Branch**: the branch you want to run (e.g. `main`, once you have
   reviewed and merged this setup).
4. **Blueprint Path**: `deploy/render/render.yaml`
5. Render shows the service `openconstructionerp` (plan **Free**) and asks
   for the values marked "sync: false":
   - `ADMIN_EMAIL` — your admin login e-mail.
   - `ADMIN_PASSWORD` — a strong password, **at least 12 characters**
     (use a password manager to generate it).
   - `DATABASE_URL` — paste the Neon **pooled** connection string.
   - `DATABASE_SYNC_URL` — **leave empty** (derived automatically). Only
     set it if you want migrations to use Neon's *direct* (non-pooler)
     string.
   - `ALLOWED_ORIGINS` — leave empty for now (see step 8).
   `JWT_SECRET` is generated by Render automatically.
6. Click **Apply** / **Deploy Blueprint**. The first build takes ~5–10
   minutes (frontend build + Python dependencies).
7. When the deploy log shows `Starting OpenConstructionERP on 0.0.0.0:…`
   and the health check is green, open the URL shown at the top of the
   service page, e.g. `https://openconstructionerp-xxxx.onrender.com`.
8. (Optional hardening) Service → **Environment** → set
   - `ALLOWED_ORIGINS` = your URL, e.g. `https://openconstructionerp-xxxx.onrender.com`
   - `ALLOWED_HOSTS` = the host only, e.g. `openconstructionerp-xxxx.onrender.com`
   then **Save, rebuild and deploy**.

### Option B — Manual web service

1. Render dashboard → **New** → **Web Service** → **Build and deploy from a
   Git repository** → pick your fork.
2. Settings:
   - *Name*: `openconstructionerp`
   - *Language / Runtime*: **Docker**
   - *Branch*: your branch
   - *Root Directory*: leave empty (repo root)
   - *Dockerfile Path*: `./deploy/docker/Dockerfile.render`
   - *Docker Build Context Directory*: `.`
   - *Instance Type*: **Free**
3. **Environment Variables** → add (see [§6](#6-environment-variable-reference)):
   - `JWT_SECRET` → click **Generate** (or paste the output of
     `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`)
   - `ADMIN_EMAIL`, `ADMIN_PASSWORD`
   - `DATABASE_URL` → Neon pooled string
4. **Advanced** → *Health Check Path*: `/api/health`
5. **Deploy Web Service**.

Render injects `PORT` (default 10000); the container listens on
`0.0.0.0:$PORT` automatically — do not hard-code a port.

### Changing an environment variable later

Service → **Environment** → edit → **Save, rebuild and deploy** (or *Save
and deploy* for env-only changes). Secrets are never shown in logs.

---

## 4. First login and day-to-day use

- Log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`. Every boot re-applies that
  password, so **changing `ADMIN_PASSWORD` in Render and redeploying is
  also how you recover a forgotten admin password**.
- **Public sign-up is disabled** on deployments (`ALLOW_SELF_REGISTRATION=false`).
  To add a colleague: temporarily set `ALLOW_SELF_REGISTRATION=true`, let
  them register (they start as read-only *viewer*), promote them in
  **Users** as admin, then set it back to `false`.
- After ~15 idle minutes the app sleeps; the first visit afterwards takes
  ~1 minute. A free uptime pinger would keep it awake but burns your 750
  hours and Neon CU-hours — not recommended.
- Cost databases (CWICR) are **not** preloaded. Import the region(s) you
  need from the Cost Database screen. On 512 MB, import one region at a
  time; very large imports may exceed the free RAM (see [§7](#7-lite-mode-for-512-mb)).

---

## 5. Durable file storage (S3-compatible bucket)

Render's free disk is wiped on every spin-down, restart and redeploy, so
uploaded files need to live somewhere else. The app has a built-in
storage layer (`backend/app/core/storage.py`) that can write files to any
**S3-compatible bucket** (AWS S3, Cloudflare R2, Backblaze B2, a MinIO
server you run yourself, …). The Render image ships the S3 client
(`aioboto3`) for this.

**What it covers today** (be precise about this before relying on it):

| Upload type | With `STORAGE_BACKEND=s3` | Bucket key | Local path with `STORAGE_BACKEND=local` (Render image) |
|---|---|---|---|
| Documents (incl. PDFs split into sheets) | ✅ bucket | `uploads/<project>/<file>` | `/data/.openestimator/uploads/<project>/` |
| Meeting transcripts (filed as documents) | ✅ bucket | `uploads/<project>/<file>` | same as documents |
| Photos and their thumbnails | ✅ bucket | `photos/<project>/…`, `photos/thumbs/<project>/…` | `/data/.openestimator/photos/` |
| PDF sheet page thumbnails | ✅ bucket | `sheets/<project>/…` | `/data/.openestimator/sheets/` |
| Takeoff PDFs | ✅ bucket | `takeoff_documents/<id>.pdf` | `/data/.openestimator/takeoff_documents/` |
| DWG/DXF drawings + parsed entities + SVG thumbnail | ✅ bucket | `dwg_uploads/…`, `dwg_entities/<id>/…`, `dwg_thumbnails/<id>/…` | `/app/data/dwg_uploads/`, `dwg_entities/`, `dwg_thumbnails/` |
| Punch-list photos | ✅ bucket | `punchlist_photos/<file>` | `/app/uploads/punchlist/photos/` |
| BIM/CAD models: geometry + original upload | ✅ bucket | `bim/<project>/<model>/…` | `/app/data/bim/` |
| BIM element table (`elements.parquet`, for the BIM data-query view) | ❌ local disk | — | `/app/data/bim/` (written when the model is uploaded) |

Downloads always go **through the app** (same routes, same permission and
path checks as before); on S3 the app streams the bytes from the bucket.
With `STORAGE_BACKEND=local` everything stays exactly where it was.

### Settings

| Variable | Value |
|---|---|
| `STORAGE_BACKEND` | `local` (default) or `s3` |
| `S3_ENDPOINT` | Provider endpoint URL, e.g. `https://<account-id>.r2.cloudflarestorage.com` or `https://s3.<region>.backblazeb2.com`. Leave empty for AWS S3. |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | An access key **scoped to this one bucket** with read + write + delete + list. Never your account's root key. |
| `S3_BUCKET` | Bucket name. |
| `S3_REGION` | Provider region, e.g. `us-east-1`; Cloudflare R2 uses `auto`. |
| `S3_PRESIGNED_DOWNLOADS` | `false` (default). See "Privacy" below. |

Leave `STORAGE_BACKEND=local` and the `S3_*` values empty for a demo
(files are lost on restart). For real use:

1. At your S3-compatible provider, create a **private** bucket (no public
   access, no website hosting) and an access key limited to that bucket.
   Providers' free allowances and sign-up requirements (some ask for a
   card) change often — check them on the provider's own pricing page.
2. Render → your service → **Environment** → set `STORAGE_BACKEND=s3` and
   fill `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`,
   `S3_REGION` → **Save, rebuild and deploy**. (With the Blueprint, the
   `S3_*` fields are prompted for when you create it.)
3. Check the deploy log for `Blob storage: S3 bucket '…'`. The app
   **refuses to start** if the bucket is unreachable or the credentials
   are wrong, rather than silently writing to the ephemeral disk.

### Privacy

- Files are uploaded **without any public ACL**; the bucket stays private.
- By default the app **streams files through its own authenticated
  routes** — browsers never receive a bucket URL, the bucket needs no CORS
  rules, and the app's Content-Security-Policy (`connect-src 'self'`)
  stays intact.
- `S3_PRESIGNED_DOWNLOADS=true` makes the 3D-viewer geometry route
  redirect to a short-lived (1 hour) presigned URL instead, which saves
  app bandwidth on large models. It only works if you also allow the
  bucket origin in the bucket's CORS rules and in the app's CSP; leave it
  off unless you need it.

### Existing files

Switching from `local` to `s3` does not copy existing files. On Render
free there is nothing to copy (the disk was already wiped). On a VPS,
copy each local directory from the table above into the bucket under its
key prefix before switching (e.g. `rclone copy
/data/.openestimator/uploads remote:<bucket>/uploads`, and likewise
`photos`, `sheets`, `takeoff_documents`, `/app/data/dwg_uploads` →
`dwg_uploads`, `/app/data/dwg_entities` → `dwg_entities`,
`/app/data/dwg_thumbnails` → `dwg_thumbnails`,
`/app/uploads/punchlist/photos` → `punchlist_photos`, `/app/data/bim` →
`bim`). The database keeps the same paths, so nothing else changes.

---

## 6. Environment variable reference

Only `JWT_SECRET` is strictly required. Everything else has a safe
default baked into `deploy/docker/Dockerfile.render`.

| Variable | Required | Default in image | Meaning |
|---|---|---|---|
| `JWT_SECRET` | **yes** | — (container refuses to start) | ≥ 32 random characters. Signs logins; also derives the key that encrypts stored AI API keys — **changing it logs everyone out and makes stored AI keys unreadable**. |
| `DATABASE_URL` | strongly recommended | SQLite in `/data` (ephemeral!) | External PostgreSQL. Neon/Render strings accepted verbatim. |
| `DATABASE_SYNC_URL` | no | derived from `DATABASE_URL` | URL used by migrations (psycopg2). Set to Neon's direct string if you prefer migrations off the pooler. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | recommended | — | Admin account created/updated every boot. Password ≥ 12 chars. |
| `PORT` | no | `8080` (Render sets `10000`) | Listen port on `0.0.0.0`. |
| `APP_ENV` | no | `production` | Disables API docs (`/api/docs`), enforces secret checks. |
| `APP_DEBUG` | no | `false` | Forced off by the entrypoint. |
| `ALLOWED_ORIGINS` | no | — | Comma-separated origins allowed for CORS. Not needed for the single-container setup (same origin); add a separate frontend URL here (e.g. a Vercel site). |
| `CORS_ORIGIN_REGEX` | no | `none` | Regex of extra allowed origins; `none` disables. |
| `ALLOWED_HOSTS` | no | `*` | Host-header allowlist, e.g. `myapp.onrender.com,*.example.com`. `/api/health` is always reachable for platform health checks. |
| `ALLOW_SELF_REGISTRATION` | no | `false` | Public sign-up. |
| `ALLOW_FIRST_USER_ADMIN` | no | `false` | "First registered user becomes admin" bootstrap — keep off on public URLs. |
| `DISABLE_DEMO_ACCOUNTS` | no | `1` (in `render.yaml`) | `1` = no demo accounts; also deactivates existing ones. |
| `SEED_DEMO` | no | `false` | Create demo accounts + 5 demo projects. |
| `DEMO_ADMIN_PASSWORD` / `DEMO_ESTIMATOR_PASSWORD` / `DEMO_MANAGER_PASSWORD` | when demo on | — | See [§8](#8-demo-accounts-on-a-public-url). |
| `WEB_CONCURRENCY` | no | `1` | Uvicorn workers. Keep `1` on 512 MB. |
| `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` | no | `5` / `5` | PostgreSQL pool. |
| `LOGIN_RATE_LIMIT` / `API_RATE_LIMIT` / `AI_RATE_LIMIT` | no | `50` / `300` / `30` per minute | Rate limits (per client IP / user). |
| `STORAGE_BACKEND` | no | `local` | `s3` = all uploaded files in an S3-compatible bucket; see [§5](#5-durable-file-storage-s3-compatible-bucket). |
| `S3_ENDPOINT` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_BUCKET` / `S3_REGION` | when `s3` | — | Bucket connection; startup fails if unreachable. |
| `S3_PRESIGNED_DOWNLOADS` | no | `false` | Redirect geometry downloads to presigned bucket URLs (needs bucket CORS + CSP change). |
| `OE_SKIP_MIGRATIONS` | no | `0` | `1` skips the boot-time migration step. |
| `DATABASE_PGBOUNCER` | no | auto for `-pooler` hosts | Force PgBouncer-safe asyncpg settings for other poolers. |

AI provider keys are entered per user in the app's settings (stored
encrypted in the database) — you do not need to put them in env vars.

---

## 7. "Lite" mode for 512 MB

The Render image **is** the lite mode — nothing heavy happens at boot:

| Feature | Lite setting | Effect |
|---|---|---|
| Vector index backfill | `VECTOR_AUTO_BACKFILL=false` | No embedding model loaded at boot. Semantic search builds on demand. |
| Vector / ML extras | not installed | No `torch` / `sentence-transformers` / `lancedb` in the image; AI features that need them degrade gracefully. LLM features (via provider REST APIs) still work. |
| Cost database (CWICR) | not preloaded | Import regions on demand from the UI. |
| Demo data | `SEED_DEMO=false` | No demo projects at boot. |
| Workers / DB pool | `WEB_CONCURRENCY=1`, pool 5+5 | Single process. |
| Redis / Celery / MinIO | not used | In-memory cache, in-process tasks, local files. |
| glibc arenas | `MALLOC_ARENA_MAX=2` | Lower fragmentation in long-running Python. |

Measured locally with `docker run -m 512m` (this branch): **~140–165 MiB
RSS after boot**, with or without the 5 demo projects. That leaves room
for normal use; very large spreadsheet / cost-database imports and big
CAD/BIM uploads are the operations most likely to hit the 512 MB ceiling.

---

## 8. Demo accounts on a public URL

Demo accounts (`demo@`, `estimator@`, `manager@openestimator.io`) use
e-mail addresses published in this repository, so on a public URL they
are only safe with passwords that only you know.

- **Default on Render: off** (`DISABLE_DEMO_ACCOUNTS=1`, `SEED_DEMO=false`).
- To enable (e.g. a public showcase with synthetic data only):
  1. `DISABLE_DEMO_ACCOUNTS=0`
  2. `SEED_DEMO=true`
  3. `DEMO_ADMIN_PASSWORD`, `DEMO_ESTIMATOR_PASSWORD`,
     `DEMO_MANAGER_PASSWORD` — three **different** strong values, each
     ≥ 12 characters, never the old published `DemoPass1234!`.
- If any of the three is missing or weak, the app **refuses to start**
  with a message naming the variable — it never falls back to a known
  password outside local development.
- Rotating a `DEMO_*_PASSWORD` and redeploying rotates that login.
- Note: `demo@` is a read-only *viewer*; `manager@` can edit data.

---

## 9. Upgrade paths (persistent disk, VPS)

When the free tier is not enough, in rough order of effort:

1. **Render Starter (~$7/month)** — no spin-down, more RAM options, and you
   can attach a **persistent disk**: service → **Disks** → mount path
   `/data`. Document/photo/sheet/takeoff uploads, caches and SQLite (if
   used) live there because the image sets `HOME=/data`; DWG drawings,
   punch-list photos and BIM/CAD files on the local backend live under
   `/app/…` (table in §5), so `STORAGE_BACKEND=s3` is the simpler way to
   make every upload durable. Keep Neon for the database or move to a paid
   Render Postgres.
2. **Small VPS + Docker Compose** (any provider, a few $/month): use
   `docker-compose.prod.yml` (bundled PostgreSQL, see [§10](#10-run-it-locally--on-a-vps-with-bundled-postgresql))
   or run this image with `-v oe_data:/data`. Put Caddy or nginx in front
   for HTTPS.
3. **Oracle Cloud Always Free** — free ARM VMs with plenty of RAM, but
   sign-up **requires a credit card** for identity verification.
4. **Object storage for uploads** — `STORAGE_BACKEND=s3` with any
   S3-compatible bucket ([§5](#5-durable-file-storage-s3-compatible-bucket)).
   Covers every upload type (§5 table).
5. **Bigger Neon plan** if you outgrow 1 GB / 100 CU-hours.

---

## 10. Run it locally / on a VPS with bundled PostgreSQL

**Same image as Render, locally:**

```bash
docker build -t oce-render -f deploy/docker/Dockerfile.render .
```

```bash
docker run --rm -p 8080:8080 -m 512m \
  -e JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  -e ADMIN_EMAIL=admin@example.com -e ADMIN_PASSWORD='choose-a-strong-one' \
  -v oe_data:/data oce-render
```

Open <http://localhost:8080>. Add `-e DATABASE_URL='<neon string>'` to
test against Neon.

**Bundled PostgreSQL (VPS / self-hosting):** `docker-compose.prod.yml`
runs PostgreSQL + backend + nginx frontend with all secrets from env:

```bash
cp .env.example .env   # then edit: POSTGRES_PASSWORD, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD
```

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

`docker-compose.quickstart.yml` is for local evaluation only (it contains
throw-away demo credentials) — never expose it to the internet.

---

## 11. Existing databases & migrations

On every boot the container runs `python -m app.scripts.db_migrate`
**before** the web server starts. It never drops or rewrites data:

| Database state | Action |
|---|---|
| SQLite | nothing (the app's own startup migrator handles SQLite) |
| Empty PostgreSQL (fresh Neon) | create all tables from the models, then `alembic stamp heads` |
| PostgreSQL with `alembic_version` | `alembic upgrade heads` (only newer migrations) |
| PostgreSQL with tables but **no** `alembic_version` (created by an older version) | left untouched, warning in the log |

For the last case, once, from a machine that can reach the database:

```bash
cd backend && DATABASE_SYNC_URL='<direct connection string>' alembic stamp <revision-matching-your-schema>
```

If a migration fails, the container exits instead of serving a
half-migrated database; fix the cause and redeploy.

Back up before upgrades: Neon offers a limited restore window (check the
current free-plan limits on neon.com); for your own copy run
`pg_dump '<direct connection string>' > backup.sql` from your machine.

---

## 12. Security checklist

What this setup enforces:

- [x] No secrets in the repo or image; `JWT_SECRET` mandatory (≥ 32 chars,
      published example values rejected) — container exits otherwise.
- [x] `APP_ENV=production`: `/api/docs`, `/api/redoc`, `/api/openapi.json`
      disabled; debug off.
- [x] Public self-registration and first-user-becomes-admin **off**;
      admin provisioned from env.
- [x] Demo accounts off by default; strong per-deployment passwords
      required when on.
- [x] Login/registration/password-reset rate limiting keyed on the
      client IP the platform proxy saw (spoofed `X-Forwarded-For` entries
      ignored).
- [x] Security headers: CSP, `X-Frame-Options: DENY`, `nosniff`,
      `Referrer-Policy`, `Permissions-Policy`, HSTS over HTTPS; no
      `Server` header.
- [x] CORS: no wildcard; no blanket `*.vercel.app` regex outside dev.
- [x] Optional Host allowlist (`ALLOWED_HOSTS`).
- [x] S3 file storage (when enabled) keeps the bucket private: no public
      ACLs, files streamed through the app's own routes (same checks as
      local disk), presigned URLs opt-in only; startup fails on a missing
      `aioboto3` or unreachable bucket.
- [x] Project photos and thumbnails require login, `documents.read` and
      access to the photo's project; thumbnails are `Cache-Control:
      private` (never stored by shared caches/CDNs).
- [x] Calendar (`.ics`) feed links verify the **full** API key (hash
      match), reject revoked/expired keys and only serve projects the key's
      owner can access. Existing feed links built from a full key keep
      working.
- [x] BCF/openCDE and the project-scoped list endpoints (risks, change
      orders, procurement, takeoff, markups, CDE, 5D cost model, teams …)
      only return projects the caller owns (admins: all).
- [x] Previously unauthenticated read endpoints (BCF/OpenCDE project &
      topic listings, team listings, CDE stats) now require login.

Before you put **real business data** in: read the follow-up list in the
pull request (per-project access scoping, upload storage, calendar-feed
tokens) and decide whether those matter for your use.

---

## 13. Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy log: `FATAL: JWT_SECRET is not set` | Add `JWT_SECRET` (Environment tab → Generate). |
| `FATAL: demo accounts are enabled … not set` | Set the three `DEMO_*_PASSWORD`s or `DISABLE_DEMO_ACCOUNTS=1`. |
| `Cannot connect to PostgreSQL` | Re-copy Neon's string (pooled, with `?sslmode=require`); check the Neon project isn't suspended for quota. |
| Data gone after a while | `DATABASE_URL` was not set → SQLite on ephemeral disk. Set it to Neon. |
| `Invalid host header` | `ALLOWED_HOSTS` doesn't list the hostname you used; add it or set `*`. |
| Registration says "disabled on this server" | Expected — see [§4](#4-first-login-and-day-to-day-use). |
| Instance restarted with "out of memory" | A big import exceeded 512 MB; import smaller chunks or upgrade the instance. |
| `FATAL: STORAGE_BACKEND=s3 but the 'aioboto3' package is not installed` | You are not using `Dockerfile.render`; install `aioboto3>=12.0.0` or set `STORAGE_BACKEND=local`. |
| `FATAL: S3 bucket '…' is not reachable` | Check `S3_ENDPOINT` (full `https://…` URL), `S3_REGION`, `S3_BUCKET` and that the key may access that bucket. |
| Uploaded files gone after a restart | `STORAGE_BACKEND` is still `local` on an ephemeral disk — configure a bucket ([§5](#5-durable-file-storage-s3-compatible-bucket)). |
| First request is slow | Render free spin-down (≈1 min wake-up). Expected. |
