"""Database URL normalisation for hosted PostgreSQL providers.

Managed Postgres providers (Neon, Render Postgres, Supabase, ElephantSQL…)
hand out libpq-style connection strings such as::

    postgresql://user:pass@ep-x-pooler.eu-central-1.aws.neon.tech/db?sslmode=require&channel_binding=require

That string works for psycopg2 (sync / Alembic) but NOT for SQLAlchemy's
asyncpg dialect, which forwards every query parameter to
``asyncpg.connect()`` as a keyword argument — ``sslmode`` and
``channel_binding`` are not asyncpg arguments and the connection fails.

The helpers here let operators paste the provider's string verbatim into
``DATABASE_URL`` and/or ``DATABASE_SYNC_URL``:

* async URL → ``postgresql+asyncpg://`` with ``sslmode=X`` rewritten to
  ``ssl=X`` and libpq-only parameters dropped;
* sync URL  → ``postgresql+psycopg2://`` (or plain ``postgresql://``) with
  ``ssl=X`` rewritten to ``sslmode=X``;
* a missing sync URL is derived from the async one (and vice versa).

Non-PostgreSQL URLs (SQLite) are returned unchanged.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_PG_SCHEMES = {
    "postgres",
    "postgresql",
    "postgresql+asyncpg",
    "postgresql+psycopg2",
    "postgresql+psycopg",
}

# libpq parameters asyncpg.connect() does not accept as keyword arguments.
_ASYNCPG_UNSUPPORTED = {
    "sslmode",
    "channel_binding",
    "sslrootcert",
    "sslcert",
    "sslkey",
    "sslcrl",
    "gssencmode",
    "target_session_attrs",
    "options",
    "application_name",
    "connect_timeout",
}


def is_postgres_url(url: str) -> bool:
    """True when ``url`` uses any PostgreSQL scheme/driver."""
    scheme = url.split("://", 1)[0].lower() if "://" in url else ""
    return scheme in _PG_SCHEMES


def _split(url: str) -> tuple[str, list[str], list[tuple[str, str]]]:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    return parts.scheme.lower(), [parts.netloc, parts.path, parts.fragment], query


def _join(scheme: str, rest: list[str], query: list[tuple[str, str]]) -> str:
    netloc, path, fragment = rest
    return urlunsplit((scheme, netloc, path, urlencode(query), fragment))


def to_async_url(url: str) -> str:
    """Return an asyncpg-compatible SQLAlchemy URL (no-op for non-PG URLs)."""
    if not is_postgres_url(url):
        return url
    _scheme, rest, query = _split(url)
    out: list[tuple[str, str]] = []
    have_ssl = any(k == "ssl" for k, _ in query)
    for key, value in query:
        if key == "sslmode":
            if not have_ssl and value and value != "disable":
                out.append(("ssl", value))
                have_ssl = True
            continue
        if key in _ASYNCPG_UNSUPPORTED:
            continue
        out.append((key, value))
    return _join("postgresql+asyncpg", rest, out)


def to_sync_url(url: str) -> str:
    """Return a psycopg2-compatible SQLAlchemy URL (no-op for non-PG URLs)."""
    if not is_postgres_url(url):
        return url
    _scheme, rest, query = _split(url)
    out: list[tuple[str, str]] = []
    have_sslmode = any(k == "sslmode" for k, _ in query)
    for key, value in query:
        if key == "ssl":
            if not have_sslmode and value:
                # asyncpg accepts "true"; libpq needs a mode name.
                mode = "require" if value.lower() in ("true", "1", "yes") else value
                out.append(("sslmode", mode))
                have_sslmode = True
            continue
        if key in ("prepared_statement_cache_size",):
            continue  # asyncpg-dialect only
        out.append((key, value))
    return _join("postgresql+psycopg2", rest, out)


def is_pgbouncer_host(url: str) -> bool:
    """Heuristic: Neon's pooled endpoints contain ``-pooler.`` in the host."""
    if not is_postgres_url(url):
        return False
    host = urlsplit(url).hostname or ""
    return "-pooler." in host


def normalize_pair(async_url: str, sync_url: str, *, sync_is_default: bool) -> tuple[str, str]:
    """Normalise both URLs, deriving the sync URL when only DATABASE_URL is set.

    ``sync_is_default`` tells us the sync URL was never configured (still
    the SQLite default) so it should follow the async URL instead.
    """
    if is_postgres_url(async_url):
        original = async_url
        async_url = to_async_url(async_url)
        if sync_is_default or not is_postgres_url(sync_url):
            # Derive from the ORIGINAL string so libpq-only options such as
            # channel_binding=require survive for the psycopg2 connection.
            sync_url = to_sync_url(original)
        else:
            sync_url = to_sync_url(sync_url)
    elif is_postgres_url(sync_url):
        sync_url = to_sync_url(sync_url)
    return async_url, sync_url
