"""Idempotent, non-destructive schema bootstrap / migration for container boots.

Usage::

    python -m app.scripts.db_migrate

Run by ``deploy/docker/render-entrypoint.sh`` before uvicorn starts. Safe to
run on every boot; it never drops or rewrites data.

Behaviour by database state:

* **SQLite** — nothing to do here. The application's own startup path
  (``sqlite_auto_migrate`` + ``create_all``) already handles SQLite.
* **PostgreSQL, empty database** (fresh Neon / Render / VPS database) —
  create every table from the SQLAlchemy models (``create_all``), then
  ``alembic stamp heads`` so future boots know the schema is current.
  This mirrors the upstream design where the baseline revision is a
  no-op and tables come from the models.
* **PostgreSQL with an ``alembic_version`` table** — ``alembic upgrade
  heads``: applies only migrations newer than the recorded revision.
* **PostgreSQL with app tables but no ``alembic_version``** (a database
  created by an older version via ``create_all`` only) — left untouched,
  with a warning. Stamping it blindly could hide a missing column
  migration; see DEPLOY.md ("Existing databases") for the one-off
  ``alembic stamp <revision>`` an operator should run.

Exit code is non-zero on failure so the container refuses to start
against a half-migrated database.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

logger = logging.getLogger("oe.db_migrate")

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _import_all_models() -> None:
    """Register every module's models on ``Base.metadata``."""
    import app.modules as modules_pkg

    importlib.import_module("app.core.audit")
    for info in pkgutil.iter_modules(modules_pkg.__path__):
        if not info.ispkg:
            continue
        name = f"app.modules.{info.name}.models"
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
        # Some modules keep models in a ``models`` package of their own —
        # importing the package is enough, its __init__ pulls them in.


def _alembic_config():  # noqa: ANN202 — alembic Config
    from alembic.config import Config

    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


def main() -> int:
    """Run the bootstrap; return a process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s db_migrate: %(message)s")

    from app.config import get_settings
    from app.core.db_url import is_postgres_url

    settings = get_settings()
    sync_url = settings.database_sync_url
    if not is_postgres_url(sync_url):
        logger.info("Non-PostgreSQL database — schema is handled at app startup; nothing to do.")
        return 0

    from alembic import command

    engine = create_engine(sync_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
    except Exception:
        logger.exception("Cannot connect to PostgreSQL (check DATABASE_URL / DATABASE_SYNC_URL)")
        return 2

    has_version_table = "alembic_version" in tables
    app_tables = tables - {"alembic_version"}
    cfg = _alembic_config()

    try:
        if has_version_table:
            logger.info("Existing managed schema — applying pending migrations (alembic upgrade heads)")
            command.upgrade(cfg, "heads")
        elif not app_tables:
            logger.info("Empty database — creating tables from models, then stamping Alembic heads")
            _import_all_models()
            from app.database import Base

            Base.metadata.create_all(engine)
            command.stamp(cfg, "heads")
        else:
            logger.warning(
                "Database has %d tables but no alembic_version table (legacy create_all schema). "
                "Leaving it untouched; the app will only add missing tables. "
                "See DEPLOY.md 'Existing databases' to bring it under Alembic.",
                len(app_tables),
            )
    except Exception:
        logger.exception("Database migration failed — refusing to start")
        return 1
    finally:
        engine.dispose()

    logger.info("Database schema is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
