#!/bin/sh
# OpenConstructionERP — container entrypoint for Dockerfile.render
#
# 1. Fail fast on missing / weak secrets (never start with defaults).
# 2. Pick the database: external PostgreSQL via DATABASE_URL (e.g. Neon),
#    otherwise SQLite under $OE_DATA_DIR (ephemeral on Render free!).
# 3. Run the idempotent, non-destructive schema migration step.
# 4. exec uvicorn on 0.0.0.0:$PORT with proxy headers trusted.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
set -eu

log() { printf '%s entrypoint: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "FATAL: $*"; exit 1; }

PORT="${PORT:-8080}"
OE_DATA_DIR="${OE_DATA_DIR:-/data}"
export PORT OE_DATA_DIR

# ── 1. Secrets ───────────────────────────────────────────────────────────
JWT_SECRET="${JWT_SECRET:-}"
if [ -z "$JWT_SECRET" ]; then
    die "JWT_SECRET is not set. Generate one with: python3 -c 'import secrets; print(secrets.token_urlsafe(48))' and add it as an environment variable on your host (Render: Environment tab, or let render.yaml generate it)."
fi
if [ "${#JWT_SECRET}" -lt 32 ]; then
    die "JWT_SECRET must be at least 32 characters (got ${#JWT_SECRET})."
fi
case "$JWT_SECRET" in
    change-me-in-production|openestimate-local-dev-key|oe-quickstart-change-me-in-production)
        die "JWT_SECRET is a published example value. Generate a fresh random secret." ;;
esac

if [ -n "${ADMIN_EMAIL:-}" ]; then
    _admin_pw="${ADMIN_PASSWORD:-}"
    [ -n "$_admin_pw" ] || die "ADMIN_EMAIL is set but ADMIN_PASSWORD is empty."
    [ "${#_admin_pw}" -ge 12 ] || die "ADMIN_PASSWORD must be at least 12 characters."
    unset _admin_pw
fi

case "${APP_DEBUG:-false}" in
    1|true|True|TRUE|yes) log "WARNING: APP_DEBUG is on — forcing it off for this deployment."; APP_DEBUG=false; export APP_DEBUG ;;
esac

# ── 2. Data directory + database selection ───────────────────────────────
mkdir -p "$OE_DATA_DIR" 2>/dev/null || true
if ! ( : > "$OE_DATA_DIR/.write-test" ) 2>/dev/null; then
    die "Data directory $OE_DATA_DIR is not writable by uid $(id -u). If you mounted a persistent disk, make it writable for this user."
fi
rm -f "$OE_DATA_DIR/.write-test"

if [ -n "${DATABASE_URL:-}" ]; then
    case "$DATABASE_URL" in
        sqlite*) log "Database: SQLite (from DATABASE_URL)" ;;
        postgres*) log "Database: external PostgreSQL (from DATABASE_URL; credentials not logged)" ;;
        *) die "DATABASE_URL has an unsupported scheme (expected postgresql://… or sqlite…)." ;;
    esac
else
    DATABASE_URL="sqlite+aiosqlite:///${OE_DATA_DIR}/openestimate.db"
    DATABASE_SYNC_URL="sqlite:///${OE_DATA_DIR}/openestimate.db"
    export DATABASE_URL DATABASE_SYNC_URL
    log "Database: SQLite at ${OE_DATA_DIR}/openestimate.db"
    log "WARNING: no DATABASE_URL set. On hosts with an ephemeral filesystem (Render free) ALL DATA IS LOST on every restart, redeploy or spin-down. Set DATABASE_URL to an external PostgreSQL (e.g. Neon free) to keep data."
fi
# DATABASE_SYNC_URL may be omitted: the app derives it from DATABASE_URL
# and normalises provider SSL parameters (sslmode / ssl / channel_binding).

# ── 2b. File storage ─────────────────────────────────────────────────────
case "${STORAGE_BACKEND:-local}" in
    s3)
        [ -n "${S3_BUCKET:-}" ] || die "STORAGE_BACKEND=s3 but S3_BUCKET is empty."
        log "File storage: S3-compatible bucket (credentials not logged)" ;;
    local)
        if [ -n "${S3_BUCKET:-}" ]; then
            log "WARNING: S3_BUCKET is set but STORAGE_BACKEND=local — the bucket is NOT used. Set STORAGE_BACKEND=s3."
        fi
        log "File storage: local disk. On an ephemeral filesystem (Render free) uploaded files are LOST on restart; see DEPLOY.md 'Durable file storage'." ;;
    *) die "STORAGE_BACKEND must be 'local' or 's3' (got '${STORAGE_BACKEND}')." ;;
esac

# ── 3. Schema migration (idempotent, never destructive) ──────────────────
if [ "${OE_SKIP_MIGRATIONS:-0}" != "1" ]; then
    log "Running database migrations…"
    ( cd /app/backend && python -m app.scripts.db_migrate ) || die "database migration failed (see log above)."
fi

# ── 4. Serve ─────────────────────────────────────────────────────────────
WORKERS="${WEB_CONCURRENCY:-1}"
log "Starting OpenConstructionERP on 0.0.0.0:${PORT} (workers=${WORKERS}, env=${APP_ENV:-production})"
# --proxy-headers + --forwarded-allow-ips='*': the container is only
# reachable through the platform's TLS proxy, so trust its X-Forwarded-*
# headers (needed for correct https scheme / HSTS).
exec python -m uvicorn app.main:create_app --factory \
    --app-dir /app/backend \
    --host 0.0.0.0 --port "$PORT" \
    --workers "$WORKERS" \
    --proxy-headers --forwarded-allow-ips='*' \
    --no-server-header \
    --timeout-keep-alive 30
