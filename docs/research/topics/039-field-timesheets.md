# 039. Field Time Tracking and Timesheets (GPS Clock-in / Geofencing)

## What it does

Field workers clock in and out from a phone, against a project and a cost code or WBS node. The app records the GPS position at each punch. An optional geofence (a radius or polygon around the site) flags punches made off-site, or prompts the worker to clock in when they arrive. Foremen can do crew clock-in for a whole gang. Supervisors review and approve timesheets each week, and approved hours flow into job costing (labour actuals against the estimate), certified payroll or wage reports, and payroll export.

## Already in the codebase (with file paths)

- `backend/app/modules/fieldreports/models.py`: `SiteWorkforceLog` (`oe_fieldreports_workforce`) stores headcount, `hours_worked`, `overtime_hours` and `wbs_id` per trade or company for each daily report. `SiteEquipmentLog` stores operational, standby and breakdown hours. This is aggregate diary data. It has no per-worker punches, approval workflow or timestamps per person.
- `backend/app/modules/documents/models.py`: project photos already carry `gps_lat` / `gps_lon` from EXIF, so a GPS-on-entity pattern exists.
- `backend/app/modules/projects/models.py`: `address` is a JSON field. It has no explicit site coordinates or geofence geometry.
- `backend/app/modules/schedule/service.py`: calendars with `hours_per_day` per region, which could be reused for overtime thresholds.
- I found no timesheet or clock-in module, no `navigator.geolocation` use in `frontend/src`, and no payroll connector.

**Gap:** per-worker time entries, the clock-in UX, geofence checks, an approval workflow, and an export to payroll and job cost.

## Who it helps and how much

Small contractors with 5–50 field staff currently use paper timecards or a separate app at about $6–15 per user per month (Workyard, BusyBusy, QuickBooks Time). Built-in timesheets remove double entry, which gives the owner real labour cost per cost code and feeds `full_evm` and job-cost actuals. Geofencing also reduces buddy-punching and time disputes. Value is **high for self-performing trades** and lower for pure estimating shops, which rarely track field hours.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)

**Medium.** I would build it as a new module, `backend/app/modules/timesheets/` (`manifest.py` with depends `oe_projects`, `oe_users`, `oe_contacts`).

- **Models:**
  - `TimeEntry` (worker, project, wbs/cost code, clock_in/out, lat/lon/accuracy, `inside_geofence`, source = manual | gps | crew, status = draft | submitted | approved).
  - `Geofence` (project_id, center + radius or GeoJSON polygon).
  - `TimesheetPeriod` (weekly approval).
- **Service:** compute the point-in-radius check with the haversine formula (stdlib) or the point-in-polygon check server-side. Per the AI-augmented, human-confirmed principle, this only flags punches; it never rejects them. Overtime rules come from the regional packs (us_pack for FLSA-style weekly OT, dach_pack for daily limits).
- **Events:** `timesheet.approved` updates `fieldreports` workforce totals and the cost actuals in `finance` / `full_evm`.
- **Validation rules:** these follow the "no module without validation" principle:
  - `timesheets.overlap`
  - `timesheets.outside_geofence`
  - `timesheets.daily_hours_exceeded`
  - `timesheets.missing_cost_code`
- **Frontend:** a mobile-first `features/timesheets` page using the browser Geolocation API (HTTPS only, foreground only), an offline queue, and a supervisor approval grid.
- **Integrations:** CSV export first. A QuickBooks Time or Kimai connector would be an optional plugin.
- **Privacy:** collect location only at punch time, never as a continuous track. Add a consent notice and a retention setting so employee location data is handled lawfully, for example under GDPR.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)

- **Browser Geolocation API** (`getCurrentPosition` / `watchPosition`): free and requires a secure context. Background tracking in a PWA is unreliable, so the app should use punch-time location only. https://developer.mozilla.org/docs/Web/API/Geolocation/watchPosition
- **Turf `@turf/boolean-point-in-polygon`:** MIT, handles polygons with holes, and can be used client-side for an instant "on site" indicator. https://turfjs.org/docs/api/booleanPointInPolygon
- **Server side:** a stdlib haversine for radius fences, or PostGIS `ST_Contains` where it is available (it is already on the stack list). Neither adds a dependency.
- **Kimai:** a self-hosted, open-source time tracker with a REST API. Its license is reported as AGPL-3.0; I could not confirm this from the repository's LICENSE file, so verify it. Usable as a sync target. https://www.kimai.org/en/open-source-time-tracker
- **QuickBooks Time (ex-TSheets) REST API:** covers timesheets, jobcodes, users and GPS points, with OAuth2. The docs repo is Apache-2.0. It needs a paid QuickBooks Time subscription, and sources disagree on which tier includes API access and geofencing. Intuit labels the API "legacy". https://github.com/TSheetsTeam/api_docs
- **MCP servers (community, unofficial):** `kimai-mcp` (PyPI / glazperle), several Clockify MCP servers, and `harvest-mcp-server`. These are useful for "how many hours did crew X log on project Y" questions via `erp_chat`, but I did not verify their maintenance or licenses. https://pypi.org/project/kimai-mcp/ , https://glama.ai/mcp/servers/@ratheesh-aot/clockify-mcp
- **Commercial construction-focused reference products:** Workyard (from $6/user/month, lists custom API integration) and BusyBusy ($0–14.99/user/month per Capterra). I could not verify a public API for BusyBusy or ClockShark. https://www.workyard.com/pricing

## Priority: 4/5 — labour is the largest controllable cost, and the existing workforce logs plus regional packs make a native module a moderate, high-value addition

Native per-worker time entries that feed job costing close a core small-contractor loop. Geofencing can stay a lightweight flag rather than full background tracking.

## Sources

- https://developer.mozilla.org/docs/Web/API/Geolocation/watchPosition
- https://bugzilla.mozilla.org/show_bug.cgi?id=1482733
- https://turfjs.org/docs/api/booleanPointInPolygon
- https://www.kimai.org/en/open-source-time-tracker
- https://github.com/TSheetsTeam/api_docs
- https://developer.intuit.com/app/developer/payroll-time/docs/workflows/track-time-legacy
- https://www.workyard.com/pricing
- https://www.capterra.com/p/132787/busybusy/pricing/
- https://pypi.org/project/kimai-mcp/2.15.0/
- https://glama.ai/mcp/servers/@ratheesh-aot/clockify-mcp
