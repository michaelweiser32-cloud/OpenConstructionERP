# 084. Building Permit Data (Shovels, Municipal Open Data, Accela) and Permit Tracking

## What it does
Two separate features:

1. **Permit tracking (internal):** a register of the permits each project needs, with status (submitted, corrections, issued, expired, final), jurisdiction, number, fees, expiry date and linked inspections, plus reminders before expiry or inspection dates.
2. **External permit data:** pulling permit records for leads (new permits near you or by GCs who might hire you), market benchmarks, and status checks at the authority. Sources are aggregators (Shovels), municipal open-data portals (Socrata/SODA, ArcGIS Hub, CKAN) and agency systems (Accela).

## Already in the codebase (with file paths)
- No permit entity exists. A grep for "permit" across `backend/app` only finds unrelated words like "symlinks not permitted" and GAEB comments.
- `backend/app/modules/inspections/` (models, service, router) holds inspection records. A permit could own these inspections.
- `backend/app/modules/projects/models.py` holds project metadata, including location, which can be used to search for nearby permits.
- `backend/app/modules/notifications/` and `backend/app/modules/integrations/` (email, Slack, Teams) can deliver expiry and inspection reminders.
- `backend/app/modules/us_pack/` is the natural place for US-specific data source connectors.
- `documents/` can store permit PDFs.

## Who it helps and how much
- **Small GCs and design-build firms:** a missed permit expiry or a failed inspection stops work on site. A simple permit register with reminders is useful and almost every small firm needs one. This value is **Medium-High** and applies to any jurisdiction.
- **Subcontractors and estimators** looking for work: new-permit leads in their trade and area are a lead source. This is US-centric, though. Aggregator data costs real money, and free data exists only for cities that publish open data. This value is **Medium**.
- **Benchmarking:** declared valuations are noisy and understated (**Low**).
- Outside the US, few authorities publish open APIs.

## Implementation effort
**Medium overall**, done in phases.
- **Phase 1 (Small): a new `permits` module.** It follows the standard layout: `manifest.py` depending on `oe_projects`, plus models (Permit, PermitEvent), schemas, a repository, a service and a router mounted at `/api/v1/permits/`. It links to `inspections` through an FK. It publishes events such as `permit.status_changed` and `permit.expiring` on the event bus, and `notifications` subscribes to them. Validation rules: an issued permit must have a number and an issue date; expiry must come after issue; a project in the construction phase must have no expired permits. All labels go through i18n. Frontend work is a register table plus a timeline in `frontend/src/features/permits`.
- **Phase 2 (Medium): a `PermitDataSource` provider interface** with these adapters:
  - **Socrata adapter:** a generic adapter configured per city with a domain and dataset ID. Free, with an optional app token. Ship a small seed list of known city datasets.
  - **Shovels adapter:** used when the user supplies their own API key.
  - **Accela adapter:** read-only status lookup for one record, and only where an agency has approved the app.

  Map every source to the BLDS field names as the canonical schema. Fetched records appear in a "Leads/Market" view. Nothing is imported automatically; the user confirms each record.
- **Phase 3:** `search_permits` / `get_permit_status` tools in `erp_chat/tools.py`.

## Building blocks
- **Socrata SODA API** (https://dev.socrata.com/docs/endpoints): free public read access; an app token is recommended for higher rate limits. Python client **sodapy** (https://pypi.org/project/sodapy/, MIT license). Many US cities (Chicago, NYC, LA, SF, Seattle, Austin) publish building-permit datasets this way.
- **Shovels API v2** (OpenAPI docs: https://shovels-v2.redoc.ly): a commercial aggregator of US permit and contractor data covering roughly 1,800+ jurisdictions. I could not verify pricing directly because the shovels.ai pricing page was unreachable from this environment. A third-party 2026 guide reports a free tier of about 500 credits a month, with paid tiers from about $599 a month. Confirm these figures before relying on them. This adapter should be optional, with the user bringing their own key.
- **Accela Construct API** (https://developer.accela.com/docs/construct-api-records.html): a REST API with `/v4/records` endpoints. Access requires app registration, and each agency must approve the app. There is no self-serve access to data across agencies, so the effort is high and the reach is limited.
- **BLDS (Building & Land Development Specification)** (https://github.com/open-data-standards/permitdata.org): an open permit-data schema from 2015. The repo says it is no longer actively maintained, but it is still a good canonical field list.
- **MCP servers:** I found no official Shovels MCP server. There is a third-party hosted "Shovels MCP" on Vinkius (https://vinkius.com/apps/shovels-mcp/with/claude-desktop) and a community single-city server, sf-permits-mcp, on Glama (https://glama.ai/mcp/servers/tbrennem-source/sf-permits-mcp/schema). I did not verify either and would not treat them as dependencies. I found no Accela MCP server.

## Priority: 3/5 — the internal permit register with reminders is cheap and every small builder needs it; external permit data is US-only, mostly behind paid APIs, so it should be an optional plugin.

## Sources
- https://dev.socrata.com/docs/endpoints
- https://pypi.org/project/sodapy/1.5.2
- https://shovels-v2.redoc.ly
- https://maxintel.org/building-permit-osint-guide-2026.html
- https://developer.accela.com/docs/construct-api-records.html
- https://developer.accela.com/docs/accela_construct_api_developers_guide/using_the_api/using_the_accela_construct_api.htm
- https://supergood.ai/api-report-card/accela
- https://github.com/open-data-standards/permitdata.org
- https://vinkius.com/apps/shovels-mcp/with/claude-desktop
- https://glama.ai/mcp/servers/tbrennem-source/sf-permits-mcp/schema
