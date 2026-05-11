#!/bin/bash
# OpenConstructionERP — Developer Setup Script
#
# Run this once after cloning the repo to get a local dev environment.
#
# Usage:
#   ./scripts/setup-dev.sh           # Full setup (checks Docker, installs deps, migrates DB)
#   ./scripts/setup-dev.sh --no-docker  # Skip Docker (use SQLite, no infra)
#   ./scripts/setup-dev.sh --no-migrate # Skip DB migrations

set -euo pipefail

# ── Options ──────────────────────────────────────────────────────────
USE_DOCKER=true
RUN_MIGRATE=true

for arg in "$@"; do
    case "$arg" in
        --no-docker)  USE_DOCKER=false ;;
        --no-migrate) RUN_MIGRATE=false ;;
        --help|-h)
            echo "Usage: $0 [--no-docker] [--no-migrate]"
            echo ""
            echo "  --no-docker   Skip Docker infra (uses SQLite, no PostgreSQL/Redis/MinIO)"
            echo "  --no-migrate  Skip running Alembic migrations"
            exit 0
            ;;
    esac
done

# ── Colors ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()    { echo -e "\n${BOLD}▶ $*${NC}"; }
divider() { echo -e "${BLUE}────────────────────────────────────────────${NC}"; }

# ── Prerequisite checks ──────────────────────────────────────────────
check_python() {
    local cmd
    for cmd in python3.12 python3 python; do
        command -v "$cmd" &>/dev/null || continue
        if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' &>/dev/null; then
            PYTHON_CMD="$cmd"
            return 0
        fi
    done
    return 1
}

check_node() {
    command -v node &>/dev/null || return 1
    local version
    version=$(node -e 'process.exit(parseInt(process.version.slice(1)) >= 18 ? 0 : 1)' 2>/dev/null && echo "ok" || echo "")
    [ -n "$version" ]
}

check_docker() {
    command -v docker &>/dev/null && docker info &>/dev/null 2>&1
}

# ── Main ─────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo ""
echo -e "${BOLD}  ╔═══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}  ║     OpenConstructionERP — Dev Setup           ║${NC}"
echo -e "${BOLD}  ╚═══════════════════════════════════════════════╝${NC}"
echo ""

divider

# ── 1. Check prerequisites ───────────────────────────────────────────
step "Checking prerequisites"

PYTHON_CMD=""
if check_python; then
    ok "Python 3.12+ found ($($PYTHON_CMD --version))"
else
    error "Python 3.12+ is required. Install from https://python.org/downloads"
    exit 1
fi

if check_node; then
    ok "Node.js 18+ found ($(node --version))"
else
    error "Node.js 18+ is required. Install from https://nodejs.org"
    exit 1
fi

if command -v npm &>/dev/null; then
    ok "npm found ($(npm --version))"
else
    error "npm not found. Install Node.js from https://nodejs.org"
    exit 1
fi

if $USE_DOCKER; then
    if check_docker; then
        ok "Docker found and running"
    else
        warn "Docker not available — falling back to --no-docker mode (SQLite)"
        USE_DOCKER=false
    fi
fi

# ── 2. Copy .env ─────────────────────────────────────────────────────
step "Environment configuration"

ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/.env.example"

if [ -f "$ENV_FILE" ]; then
    ok ".env already exists — skipping"
else
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    ok ".env created from .env.example"

    if ! $USE_DOCKER; then
        # Patch DATABASE_URL to use SQLite when Docker is not available
        sed -i.bak \
            -e 's|^DATABASE_URL=.*|DATABASE_URL=sqlite+aiosqlite:///./openestimate.db|' \
            -e 's|^DATABASE_SYNC_URL=.*|DATABASE_SYNC_URL=sqlite:///./openestimate.db|' \
            "$ENV_FILE"
        rm -f "$ENV_FILE.bak"
        info "Configured .env to use SQLite (no Docker)"
    fi

    warn "Review .env and set JWT_SECRET, API keys, etc. before production use."
fi

# ── 3. Backend dependencies ───────────────────────────────────────────
step "Installing backend dependencies"

cd "$REPO_ROOT/backend"

if command -v uv &>/dev/null; then
    info "Using uv (fast)..."
    uv pip install -r requirements.txt
else
    info "Using pip..."
    $PYTHON_CMD -m pip install --upgrade pip --quiet
    $PYTHON_CMD -m pip install -r requirements.txt --quiet
fi

ok "Backend dependencies installed"

# ── 4. Frontend dependencies ──────────────────────────────────────────
step "Installing frontend dependencies"

cd "$REPO_ROOT/frontend"
npm install --silent
ok "Frontend dependencies installed"

# ── 5. Start Docker infrastructure ───────────────────────────────────
if $USE_DOCKER; then
    step "Starting infrastructure (PostgreSQL, Redis, MinIO)"

    cd "$REPO_ROOT"
    docker compose up -d postgres redis minio

    info "Waiting for PostgreSQL to be ready..."
    local_tries=0
    until docker compose exec -T postgres pg_isready -U oe -d openestimate &>/dev/null; do
        local_tries=$((local_tries + 1))
        if [ "$local_tries" -ge 30 ]; then
            error "PostgreSQL did not become ready in time. Check: docker compose logs postgres"
            exit 1
        fi
        sleep 1
    done

    ok "PostgreSQL is ready"
    ok "Redis is running"
    ok "MinIO is running (http://localhost:9001 — admin/minioadmin)"
fi

# ── 6. Database migrations ────────────────────────────────────────────
if $RUN_MIGRATE; then
    step "Running database migrations"

    cd "$REPO_ROOT/backend"
    alembic upgrade head
    ok "Migrations applied"
fi

# ── 7. Done ───────────────────────────────────────────────────────────
divider
echo ""
echo -e "${GREEN}${BOLD}  Setup complete!${NC}"
echo ""
echo "  Start the app:"
echo -e "    ${BOLD}make dev${NC}                   # backend + frontend"
echo -e "    ${BOLD}make dev-backend${NC}            # FastAPI only  → http://localhost:8000"
echo -e "    ${BOLD}make dev-frontend${NC}           # Vite only     → http://localhost:5173"
echo ""
echo "  Useful commands:"
echo -e "    ${BOLD}make test${NC}                   # Run all tests"
echo -e "    ${BOLD}make lint${NC}                   # Lint backend + frontend"
echo -e "    ${BOLD}make migrate-new MSG=\"...\"${NC}  # Create a new migration"
if $USE_DOCKER; then
echo -e "    ${BOLD}make stop${NC}                   # Stop Docker services"
fi
echo ""
