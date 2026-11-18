# 055. Daily Reports / Site Diary (weather, manpower, equipment, delays)

## What it does
A daily site diary records each working day: weather, crews and headcounts by trade, plant and equipment on site, work done, delays and their causes, visitors, safety notes, photos, and a sign-off. For a small contractor the diary is the main evidence for extension-of-time and weather-delay claims, for checking labour cost against the estimate, and for resolving disputes months later.

## Already in the codebase (with file paths)
The basic feature is largely built:
- `backend/app/modules/fieldreports/models.py` has a `FieldReport` with weather condition and temperature, a `weather_data` JSON field, workforce and equipment lists, `delays` plus `delay_hours`, photos and signature. There are also structured `SiteWorkforceLog` and `SiteEquipmentLog` tables.
- `backend/app/modules/fieldreports/router.py` (about 1,050 lines) provides CRUD, submit and approve, a calendar view, a summary, CSV/Excel import with a template, export, PDF export per report, document linking, and workforce and equipment log endpoints.
- `backend/app/modules/fieldreports/weather.py` fetches current weather from OpenWeatherMap. It needs an API key and returns nothing without one.
- On the frontend, `frontend/src/features/fieldreports/FieldReportsPage.tsx` is the page, and `frontend/src/shared/lib/offlineStore.ts` provides offline storage.

**Gaps:**
1. Weather is current-only. There is no historical or backdated lookup, so a report filled in the next morning gets the wrong day's weather, and there is no keyless provider.
2. `fieldreports` publishes no events, and `schedule`, `full_evm` and `changeorders` never reference it. Delays do not flow into the schedule, EOT/claims or change orders.
3. There is no rollup of labour hours against BOQ or estimate productivity, and no weather-day statistics (rain days against contract thresholds).
4. `erp_chat/tools.py` has no field-report tools, so there is no AI drafting from voice or notes and no "summarise last week's delays" query.

## Who it helps and how much
- **Site supervisors and foremen (High):** a faster daily entry with auto-filled weather and yesterday's crew copied forward cuts the paperwork that often gets skipped.
- **Owners and PMs of small general contractors (High):** a dated, approved diary with objective weather data supports delay claims and makes it easy to spot productivity drift.
- **Estimators (Medium):** real man-hours per BOQ item feed back into future unit rates.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch)
**Medium**, mostly extending what exists rather than building new.
1. **Weather provider abstraction** in `fieldreports/weather.py`. Add a keyless default provider (Open-Meteo forecast plus historical archive, or Bright Sky for DACH) and keep OpenWeatherMap as an option. Allow a date parameter so backdated reports get the right weather. Store the provider and data attribution in `weather_data`.
2. **Events:** publish `fieldreports.report.approved` and `fieldreports.delay.recorded` on the core event bus. Handlers in `schedule` (flag affected activities), `changeorders` (draft an EOT/claim for human confirmation) and `full_evm` (actual labour hours) subscribe to them.
3. **Validation rules** (a `fieldreports/validators.py` set):
   - delay hours without a cause
   - a working day with zero workforce
   - equipment logged without hours
   - a report not submitted within 24 hours
4. **AI and MCP:** add `erp_chat` tools such as `list_field_reports`, `summarize_delays` and `draft_field_report` (from voice or text, shown with a confidence score and confirmed by the user). This follows the AI-augmented, human-confirmed principle.
5. **Frontend:** "copy from yesterday", automatic weather, and a delay and weather-day chart.

## Building blocks (free/open-source libs, APIs, MCP servers)
- **Open-Meteo API** (https://open-meteo.com/): needs no key and covers forecasts and historical data. The data is CC BY 4.0 with attribution. The free tier is limited to **non-commercial** use (about 10k calls/day). Commercial use requires a paid plan (https://open-meteo.com/en/pricing; prices not verified). The server itself is open source and can be self-hosted (https://github.com/open-meteo/open-meteo).
- **Bright Sky** (https://brightsky.dev/): an MIT-licensed, keyless JSON API over German DWD station observations and MOSMIX forecasts, free for all purposes. DWD terms apply to the data. A good fit for `dach_pack`.
- **OpenWeatherMap One Call 3.0** (https://openweathermap.org/api): 1,000 calls/day free, then pay per call (about GBP 0.0012 per call according to OpenWeather pages). This is the provider already integrated.
- **Weather MCP servers:**
  - isdaniel/mcp_weather_server, Python, Apache-2.0, Open-Meteo (https://github.com/isdaniel/mcp_weather_server)
  - gbrigandi/mcp-server-openmeteo, Rust (https://github.com/gbrigandi/mcp-server-openmeteo)
  - Both are community projects, not official. Their maintenance status is unverified.
- **Procore Daily Log API** for import and interoperability: it has weather, delay, manpower and equipment log resources (https://developers.procore.com/). The endpoint paths were seen only in third-party docs, so verify them before building an importer.
- **Existing stack:** `httpx` (already used) and the existing PDF export. No new dependencies are needed.

## Priority: 4/5
The core diary already exists. Adding keyless historical weather, linking delays to schedule and claims, and AI drafting turns it from a form into claim-grade evidence at medium effort.

## Sources
- https://open-meteo.com/
- https://open-meteo.com/en/pricing
- https://github.com/open-meteo/open-meteo
- https://brightsky.dev/
- https://api.brightsky.dev/openapi.json
- https://openweathermap.org/api
- https://github.com/isdaniel/mcp_weather_server
- https://mcpservers.org/servers/gbrigandi/mcp-server-openmeteo
- https://support.procore.com/products/online/user-guide/company-level/analytics/reports-subpage/daily-logs-report
- https://developers.procore.com/
