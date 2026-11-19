"""Tests for internet-deployment hardening (DEPLOY.md / Dockerfile.render).

Covers:
* X-Forwarded-For client resolution used by the rate limiters
* hosted-Postgres URL normalisation (Neon / Render connection strings)
* demo-account password policy (DISABLE_DEMO_ACCOUNTS / DEMO_*_PASSWORD)
* self-registration / first-user-admin defaults per APP_ENV
* Host-header allowlist matching
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.core.db_url import is_pgbouncer_host, normalize_pair, to_async_url, to_sync_url
from app.core.rate_limiter import _client_from_forwarded_for
from app.middleware.trusted_host import host_is_allowed

# ── X-Forwarded-For ──────────────────────────────────────────────────────


class TestForwardedFor:
    def test_single_public_ip(self) -> None:
        assert _client_from_forwarded_for("8.8.8.8") == "8.8.8.8"

    def test_spoofed_left_entries_are_ignored(self) -> None:
        # Client sent "1.1.1.1"; the platform edge appended the real 9.9.9.9.
        assert _client_from_forwarded_for("1.1.1.1, 9.9.9.9") == "9.9.9.9"

    def test_internal_hops_on_the_right_are_skipped(self) -> None:
        assert _client_from_forwarded_for("1.1.1.1, 9.9.9.9, 10.0.0.5, 172.16.0.2") == "9.9.9.9"

    def test_garbage_entries_are_skipped(self) -> None:
        assert _client_from_forwarded_for("not-an-ip, 9.9.9.9, unknown") == "9.9.9.9"

    def test_all_private_falls_back_to_leftmost(self) -> None:
        assert _client_from_forwarded_for("192.168.1.20, 10.0.0.1") == "192.168.1.20"

    def test_empty(self) -> None:
        assert _client_from_forwarded_for(" , ") == ""

    def test_ipv6_public(self) -> None:
        assert _client_from_forwarded_for("::1, 2606:4700:4700::1111") == "2606:4700:4700::1111"


# ── Database URLs ────────────────────────────────────────────────────────

NEON_POOLED = (
    "postgresql://app_user:secretpw@ep-example-123456-pooler.eu-central-1.aws.neon.tech/"
    "neondb?sslmode=require&channel_binding=require"
)


class TestDatabaseUrls:
    def test_async_url_from_neon_string(self) -> None:
        url = to_async_url(NEON_POOLED)
        assert url.startswith("postgresql+asyncpg://app_user:secretpw@ep-example-123456-pooler.")
        assert "ssl=require" in url
        assert "sslmode" not in url
        assert "channel_binding" not in url

    def test_sync_url_keeps_libpq_params(self) -> None:
        url = to_sync_url(NEON_POOLED)
        assert url.startswith("postgresql+psycopg2://")
        assert "sslmode=require" in url
        assert "channel_binding=require" in url

    def test_sync_url_translates_asyncpg_ssl(self) -> None:
        assert to_sync_url("postgresql+asyncpg://u:p@h/db?ssl=true").endswith("?sslmode=require")

    def test_postgres_scheme_alias(self) -> None:
        assert to_async_url("postgres://u:p@h:5432/db").startswith("postgresql+asyncpg://u:p@h:5432/db")

    def test_sqlite_untouched(self) -> None:
        assert to_async_url("sqlite+aiosqlite:////data/x.db") == "sqlite+aiosqlite:////data/x.db"
        assert to_sync_url("sqlite:////data/x.db") == "sqlite:////data/x.db"

    def test_sync_derived_when_only_async_given(self) -> None:
        a, s = normalize_pair(NEON_POOLED, "sqlite:///./openestimate.db", sync_is_default=False)
        assert a.startswith("postgresql+asyncpg://")
        assert s.startswith("postgresql+psycopg2://")
        assert "channel_binding=require" in s

    def test_explicit_sync_url_respected(self) -> None:
        direct = NEON_POOLED.replace("-pooler", "")
        _a, s = normalize_pair(NEON_POOLED, direct, sync_is_default=False)
        assert "-pooler" not in s

    def test_pgbouncer_detection(self) -> None:
        assert is_pgbouncer_host(to_async_url(NEON_POOLED))
        assert not is_pgbouncer_host("postgresql+asyncpg://u:p@db.internal/x")
        assert not is_pgbouncer_host("sqlite:///x.db")

    def test_settings_apply_normalisation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", NEON_POOLED)
        monkeypatch.delenv("DATABASE_SYNC_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.database_url.startswith("postgresql+asyncpg://")
        assert "ssl=require" in s.database_url
        assert s.database_sync_url.startswith("postgresql+psycopg2://")


# ── Registration defaults ────────────────────────────────────────────────


class TestRegistrationDefaults:
    @pytest.mark.parametrize("env", ["production", "staging"])
    def test_closed_outside_development(self, env: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ALLOW_SELF_REGISTRATION", raising=False)
        monkeypatch.delenv("ALLOW_FIRST_USER_ADMIN", raising=False)
        s = Settings(_env_file=None, app_env=env)
        assert s.self_registration_enabled is False
        assert s.first_user_admin_enabled is False

    def test_open_in_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ALLOW_SELF_REGISTRATION", raising=False)
        monkeypatch.delenv("ALLOW_FIRST_USER_ADMIN", raising=False)
        s = Settings(_env_file=None, app_env="development")
        assert s.self_registration_enabled is True
        assert s.first_user_admin_enabled is True

    def test_explicit_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOW_SELF_REGISTRATION", "true")
        s = Settings(_env_file=None, app_env="production")
        assert s.self_registration_enabled is True
        assert s.first_user_admin_enabled is False


# ── Demo account passwords ───────────────────────────────────────────────

_DEMO_VARS = ("DEMO_ADMIN_PASSWORD", "DEMO_ESTIMATOR_PASSWORD", "DEMO_MANAGER_PASSWORD")


class TestDemoPasswords:
    @pytest.fixture(autouse=True)
    def _clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in _DEMO_VARS:
            monkeypatch.delenv(var, raising=False)

    def test_development_keeps_legacy_default(self) -> None:
        from app.main import _resolve_demo_passwords

        resolved = _resolve_demo_passwords("development")
        assert set(resolved.values()) == {None}

    def test_production_requires_passwords(self) -> None:
        from app.main import _resolve_demo_passwords

        with pytest.raises(RuntimeError, match="DEMO_ADMIN_PASSWORD is not set"):
            _resolve_demo_passwords("production")

    def test_production_rejects_weak_and_legacy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.main import _resolve_demo_passwords

        monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "DemoPass1234!")
        monkeypatch.setenv("DEMO_ESTIMATOR_PASSWORD", "short")
        monkeypatch.setenv("DEMO_MANAGER_PASSWORD", "a-long-enough-pass-phrase")
        with pytest.raises(RuntimeError, match="too weak"):
            _resolve_demo_passwords("production")

    def test_production_accepts_strong(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.main import _resolve_demo_passwords

        for i, var in enumerate(_DEMO_VARS):
            monkeypatch.setenv(var, f"unit-test-strong-pass-{i}")
        resolved = _resolve_demo_passwords("production")
        assert resolved["demo@openestimator.io"] == "unit-test-strong-pass-0"
        assert resolved["manager@openestimator.io"] == "unit-test-strong-pass-2"


# ── Host allowlist ───────────────────────────────────────────────────────


class TestHostAllowlist:
    def test_exact_and_port(self) -> None:
        assert host_is_allowed("erp.example.com:443", ["erp.example.com"])
        assert not host_is_allowed("evil.example.com", ["erp.example.com"])

    def test_wildcard_subdomain(self) -> None:
        assert host_is_allowed("my-app.onrender.com", ["*.onrender.com"])
        assert not host_is_allowed("onrender.com", ["*.onrender.com"])
        assert not host_is_allowed("onrender.com.evil.io", ["*.onrender.com"])

    def test_star_and_empty_host(self) -> None:
        assert host_is_allowed("anything", ["*"])
        assert not host_is_allowed("", ["erp.example.com"])
