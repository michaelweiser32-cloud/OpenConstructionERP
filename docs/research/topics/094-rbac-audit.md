# 094. RBAC and audit log (role templates, field-level permissions, tamper-evident audit)

## What it does
Controls who can see and change what, and keeps a trustworthy record of what changed. The feature has three parts:
- **Role/permission templates:** reusable bundles such as "Estimator", "Site Manager", "Subcontractor (external)" or "Accountant", assigned per project. Procore works this way: each tool gets a None / Read Only / Standard / Admin level, and granular add-ons cover specific actions.
- **Field-level permissions:** hide or lock sensitive fields such as unit rates, markup, margin, labour cost and supplier prices from some roles. One example is letting a subcontractor see quantities without seeing your rates.
- **Tamper-evident audit:** an append-only log where each row is hash-chained to the one before it, so any edit or deletion of history can be detected. This supports claims, disputes, change-order evidence and ISO 9001/19650 style traceability.

## Already in the codebase (with file paths)
- `backend/app/core/permissions.py`: a global `PermissionRegistry` with `{module}.{action}` permissions. There are four hierarchical roles (admin > manager > editor > viewer), plus `ROLE_ALIASES` that map titles like estimator and QS onto those four. Each permission has a single minimum role, and the scheme has no project scope and no custom roles.
- `backend/app/dependencies.py` (`RequirePermission`): an endpoint guard used in about 500 places, so it is a good place to hook in a richer engine.
- `backend/app/modules/users/models.py`: `User.role` is one string column, with no per-project role. `backend/app/modules/teams/` and `modules/users/permissions.py` exist.
- `backend/app/core/audit.py` + `audit_router.py`: an `oe_core_audit_log` table (action, entity, user, IP, JSON details) with list and entity-trail endpoints gated by `audit.view`. It has no `prev_hash`/`row_hash` and no append-only enforcement. Only a handful of modules call `audit_log()` directly. `core/activity_feed.py` is a separate user-facing feed.
- I found no field-level masking layer in the schemas.

**Gap:** project-scoped roles, editable role templates, field masking in the response schemas, a hash chain with verification, consistent audit calls through the event bus, and a frontend admin UI.

## Who it helps and how much
- **Small GC / estimating firms (5-30 users):** high value. The top request is to hide rates and margins from juniors, site staff and external partners, and to let externals see only their project. The ERP is sensitive to rates and markups, so this is close to a must-have once more than one person uses it.
- **Owners and directors:** a tamper-evident trail of price and quantity changes helps in change-order disputes and payment claims. It also builds trust when the system is self-hosted.
- **Solo estimators:** low value.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium overall.** The work splits into three phases.
1. **Role templates and project scope (M):** add `oe_users_role_template` (name, permission set as JSON, built-in templates seeded per regional pack) and `oe_projects_member` (user, project, template). `RequirePermission` then resolves the project from the path and checks the template, falling back to the global role. Modules keep registering permissions through their manifests, so the registry becomes the catalogue that templates pick from.
2. **Field-level permissions (S-M):** modules declare sensitive fields in their permissions.py (e.g. `boq.field.unit_rate.read`). A response hook (`core/hooks.py` filter `serialize.<entity>`) masks or nulls those fields before Pydantic output. Writes to locked fields are rejected in the service layer. Exports (GAEB/Excel/PDF in reporting) must use the same filter.
3. **Tamper-evident audit (S):** add `seq`, `prev_hash` and `row_hash` (SHA-256 over canonical JSON plus prev_hash) to `oe_core_audit_log`. Serialise writes with `pg_advisory_xact_lock` on PostgreSQL, or a single-writer lock on SQLite. On PostgreSQL, add a trigger that blocks UPDATE/DELETE. Add a `/audit/verify` endpoint and a periodic signed checkpoint to object storage, which catches truncation of the newest entries. A generic event-bus subscriber (`core/events.py`) audits every `*.created/updated/deleted` event so modules get coverage for free.
Frontend: a permission-matrix editor (templates × module permissions), a project members tab and an audit viewer with a "chain verified" badge.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **PyCasbin**: RBAC with domains, where a domain can be a project. It has an async enforcer and is Apache-2.0. It is optional, since the existing registry could be extended instead. https://github.com/apache/casbin-pycasbin
- **OpenFGA**: Zanzibar-style relationship-based access control (ReBAC), Apache-2.0. It runs as a separate server, which is too heavy for the 2GB VPS target, but it is a useful design reference. https://pypi.org/project/openfga-sdk/
- **Cerbos**: a policy decision point and open-core service. Its Python SDK is listed as open source, but I did not verify the exact SDK license. https://cerbos.dev/ecosystem/python
- **pgAudit**: PostgreSQL-level statement audit under the PostgreSQL License. It is an optional ops-level complement and does not replace the application log. https://github.com/pgaudit/pgaudit
- **SQLAlchemy-Continuum**: row versioning and history tables, BSD-3-Clause. It could back field-level "who changed the rate" history. https://github.com/kvesteri/sqlalchemy-continuum
- **Hash-chain design references:** a PostgreSQL pattern write-up at https://appmaster.io/blog/tamper-evident-audit-trails-postgresql. waxseal (MIT, early stage, unverified maturity) at https://pypi.org/project/waxseal/. immudb is a tamper-proof database, but adopting it would mean a second database, which conflicts with the single-database principle.
- **MCP:** I found no dedicated RBAC or audit MCP server worth integrating. Instead, the existing `erp_chat/tools.py` should enforce the same permission and field masks, and audit tool calls with actor "ai".

## Priority: 4/5 — Hiding rates and margins and giving externals project-scoped access are expected in any multi-user estimating tool, and the existing registry, guard and audit table make the gap a Medium-effort extension.

## Sources
- https://support.procore.com/products/online/user-guide/company-level/permissions
- https://support.procore.com/products/online/user-guide/company-level/permissions/tutorials/grant-granular-permissions-in-a-project-permissions-template
- https://casbin.apache.org/docs/rbac-with-domains
- https://github.com/apache/casbin-pycasbin
- https://pypi.org/project/openfga-sdk/
- https://cerbos.dev/ecosystem/python
- https://www.enterprisedb.com/docs/pg_extensions/pgaudit/
- https://github.com/kvesteri/sqlalchemy-continuum
- https://appmaster.io/blog/tamper-evident-audit-trails-postgresql
- https://pypi.org/project/waxseal/
