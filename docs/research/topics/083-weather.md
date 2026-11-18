# 083. Job-site weather (Open-Meteo, NWS API, OpenWeather) for daily reports and delay claims

## What it does
Records the weather at each project site automatically: hourly and daily temperature, precipitation, wind and conditions, tied to the site coordinates and the report date. The daily report gets pre-filled. The stored series becomes evidence for weather-delay claims and extension-of-time (EOT) requests: actual rain, frost or wind days are compared with contract thresholds and a historical "normal" baseline, and the excess days are flagged on the schedule.

## Already in the codebase (with file paths)
- `backend/app/modules/fieldreports/weather.py`: calls the OpenWeatherMap **2.5 current-weather** endpoint (`/data/2.5/weather`), returns None if no key. It only gives the weather *now*, not the weather for the report date. There is no forecast, history or daily aggregate.
- `backend/app/config.py`: `openweathermap_api_key` setting.
- `backend/app/modules/fieldreports/router.py`: `GET /weather/` endpoint, plus import/export of `weather_condition` (enum: clear, cloudy, rain, snow, fog, storm).
- `backend/app/modules/fieldreports/models.py`: `weather_condition`, `temperature_c`, `wind_speed`, `precipitation`, `humidity` and a `weather_data` JSON column.
- `frontend/src/shared/ui/ProjectWeather/ProjectWeather.tsx`: a project widget that calls the Open-Meteo forecast **directly from the browser** (keyless, up to 16 days).

**Gaps:**
- Two providers are used with no shared abstraction.
- No historical backfill for back-dated reports.
- No weather-day calculation, contract threshold rules, or link to `schedule` or `changeorders` for delay claims.
- No validation rule such as "report weather disagrees with the recorded data".
- No NWS support.
- Licensing: Open-Meteo's free tier is for non-commercial use, which matters for commercial deployments.

## Who it helps and how much
- **Site supers and foremen:** no more manual weather entry, so less daily-report friction.
- **Owners and PMs of small general contractors and subcontractors:** defensible, timestamped weather records for EOT and delay claims under clauses in AIA, NEC, FIDIC and VOB/B style contracts. One approved weather-delay claim can be worth more than the whole software cost.
- **Estimators:** historical rain and frost days per month help price winter work and set schedule contingency.

Value is high for anyone doing outdoor work.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.**
- **Provider layer:** create a `WeatherProvider` protocol in a new `backend/app/modules/weather/` module, with a manifest that depends on `oe_projects`. It would have three adapters:
  - Open-Meteo, the default for forecast and archive.
  - NWS, for US forecast, station observations and alerts.
  - OpenWeather, the existing key-based option, upgraded to One Call 3.0 `day_summary`.
  - Provider and base URL are set in config. The Open-Meteo base URL can point to a self-hosted instance.
- **Storage:** a `SiteWeatherDay` table (project_id, date, source, raw JSON, normalized fields), filled by a daily background task and backfilled on demand.
- **Events and hooks:** `fieldreports.report.created` triggers a hook that pre-fills the weather fields, which the user then confirms. A `weather.day.adverse` event lets `schedule` and `changeorders` propose (not auto-apply) weather-delay entries.
- **Validation:**
  - `weather.report_consistency`: warns when a report says "clear" but more than 5 mm of rain was recorded.
  - `weather.threshold_exceeded`: shows info when a day crosses a contract threshold.
- **Frontend and integrations:**
  - The widget should go through the backend proxy, for caching and the NWS User-Agent requirement.
  - A "Weather-day log" PDF/Excel export goes into `reporting`.
  - An `erp_chat` tool, `get_site_weather(project, date_range)`.
- **i18n:** all condition labels.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Open-Meteo:** forecast, historical archive and geocoding, keyless.
  - The free tier is non-commercial. Commercial use needs a paid plan, and third-party sources say historical APIs need a higher tier. Prices could not be checked against the official page in this session.
  - The server software is open source, so self-hosting is an alternative.
  - https://open-meteo.com/en/pricing
- **NWS API (api.weather.gov):** free, no key, public-domain US government data. It requires a User-Agent header, and browser CORS has issues when a custom User-Agent is set. Covers forecasts, `/stations/{id}/observations` and alerts. US only.
- **OpenWeather One Call 3.0:** 1,000 calls/day free, then pay per call. It has `timemachine` and `day_summary` for historical daily data. A key and billing details are required.
- **NOAA NCEI Climate Data Online (GHCN-Daily):** official US station history, often preferred as claim evidence. Its token terms were not verified in this session.
- **Meteostat Python:** MIT-licensed code, CC BY 4.0 data, station-based history worldwide. Useful for "normal" baselines.
- **Bright Sky:** a DWD open-data JSON API relevant for DACH. It exists, but its terms were not verified in this session.
- **MCP servers (community, not official vendor servers):**
  - `isdaniel/mcp_weather_server`: Open-Meteo, Apache-2.0.
  - `weather-mcp/weather-mcp`: NOAA plus Open-Meteo fallback, MIT.
  - `dgahagan/weather-mcp`: listed in the official MCP registry.
  - These are fine for ad-hoc chat queries. The ERP should still store its own records so claim evidence stays auditable.

## Priority: 4/5 — the basics exist but only capture current weather. Historical capture per site plus weather-day logs for delay claims is a cheap, high-ROI step for small contractors.

## Sources
- https://open-meteo.com/en/pricing
- https://open-meteo.com/
- https://openmeteo.substack.com/p/api-subscriptions-for-commercial
- https://www.weather.gov/documentation/services-web-api
- https://github.com/weather-gov/api/discussions/312
- https://old.openweathermap.org/api/one-call-3
- https://openweathermap.org/api
- https://github.com/meteostat/meteostat-python
- https://dev.meteostat.net/
- https://mcpservers.org/servers/isdaniel/mcp_weather_server
- https://github.com/weather-mcp
- https://claudemarket.ai/mcp/dgahagan/weather-mcp
