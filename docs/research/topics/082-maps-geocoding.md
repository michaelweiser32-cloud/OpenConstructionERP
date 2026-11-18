# 082. Maps and geocoding for job sites

## What it does
Turns a project address into coordinates (geocoding) and coordinates back into addresses (reverse geocoding), and draws job sites on a map. For a small contractor this helps with: a portfolio map of all active and bid projects, a site pin on every project, mapped GPS photos and field reports, distance and drive time from the yard (to price travel, mobilisation and delivery), local weather, and address autocomplete when creating projects or contacts.

## Already in the codebase (with file paths)
- `frontend/src/shared/ui/ProjectMap/ProjectMap.tsx`: a single-project map built on MapLibre GL (`react-map-gl/maplibre`). It uses OpenFreeMap "liberty" vector tiles with a CartoDB raster fallback. It geocodes in the browser against public Nominatim (`nominatim.openstreetmap.org/search`) and caches results in `localStorage` for 30 days. An `onResolved` callback lets the parent save the coordinates.
- `frontend/src/features/projects/api.ts` and `ProjectDetailPage.tsx`: once resolved, coordinates are stored in project metadata.
- `backend/app/modules/projects/models.py`: `address` is a JSON column. There are no typed lat/lng columns and no spatial index.
- `frontend/src/shared/ui/ProjectWeather/ProjectWeather.tsx` (Open-Meteo, keyless) and `backend/app/modules/fieldreports/router.py` `/weather/` (OpenWeatherMap, needs a key): two separate weather paths.
- `backend/app/modules/documents/models.py`: photos have `gps_lat`/`gps_lon` from EXIF, but nothing shows them on a map.
- `frontend/package.json`: `leaflet` and `react-leaflet` are installed, but no source file imports them (likely dead dependencies).

**Gap:** there is no backend geocoding service and no provider abstraction (OSM, Mapbox or Google). Every client calls public Nominatim directly, so the 1 request/second limit applies to the whole application and is hard to respect. There is also no multi-project or portfolio map, no map layer for photos or field reports, no reverse geocoding, no distance or travel-time calculation, no autocomplete, and no MCP or `erp_chat` tool for location questions.

## Who it helps and how much
- Owners and estimators doing bid/no-bid decisions: a map of bids and won work by region, plus the distance from the yard to price travel and mobilisation. Medium value.
- Site supervisors and field crews: photos, punch items and reports tied to a location. Medium value.
- Office staff: autocomplete reduces bad addresses. Low to medium value.

None of this is core estimating. It is polish that makes the tool feel complete and that makes travel-cost line items easier to justify.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Small to Medium.** Create a new `backend/app/modules/geo/` module (manifest `oe_geo`, depends on `oe_projects`):
- `service.py` has a `GeocoderProvider` protocol with these implementations: Nominatim (default, with a configurable base URL for self-hosted instances), Photon, Mapbox and Google. A key unlocks a provider through settings.
- A server-side cache table and a 1 request/second throttle, with an identifying User-Agent.
- `router.py` exposes `/api/v1/geo/geocode`, `/reverse` and `/distance`. Distance is haversine by default; OSRM or a provider's routing API is optional.
- An event handler on `project.created`/`project.updated` geocodes the project and stores typed `lat`/`lng`.
- Validation rules: missing coordinates, or a geocode result outside the project's country.
- An `erp_chat/tools.py` tool: "projects within 50 km".

Frontend: point `ProjectMap` at the backend endpoint, and add a portfolio map with clustering (MapLibre supports clustering natively) and a photo layer. Remove the unused Leaflet dependency. Respect attribution requirements and add i18n strings.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- MapLibre GL JS (https://github.com/maplibre/maplibre-gl-js): BSD-3, already in use.
- OpenFreeMap tiles (https://openfreemap.org): free and keyless according to the project's own code comment. I could not fetch the site from this session to confirm the terms.
- Nominatim (https://nominatim.org, policy at https://operations.osmfoundation.org/policies/nominatim/): GPL-2 software, ODbL data. The public endpoint allows at most 1 request/second for the whole application, requires an identifying User-Agent or Referer, and discourages bulk use. Self-hosting is possible.
- Photon (https://github.com/komoot/photon): Apache-2.0, typo-tolerant search suited to autocomplete. The public API is throttled; self-hosting is recommended.
- Mapbox (https://www.mapbox.com/pricing): third-party summaries list 100k temporary geocodes and 50k web map loads free per month. Permanent (storable) geocoding is paid, about $5 per 1,000. This was not verified on mapbox.com.
- Google Maps Platform (https://developers.google.com/maps/billing-and-pricing/march-2025): since March 2025, free usage is set per SKU. The Essentials tier, which covers Geocoding, includes 10,000 free events per month.
- MCP servers: Google's hosted Maps Grounding Lite MCP (https://developers.google.com/maps/ai/grounding-lite) offers places, weather and routes and needs an API key. The community `cyanheads/openstreetmap-mcp-server` (https://glama.ai/mcp/connectors/io.github.cyanheads/openstreetmap-mcp-server) offers Nominatim and Overpass. I did not audit its maintenance or license.

## Priority: 2/5 — the basics (single-site map plus geocoding) already exist. The rest adds convenience, not core estimating value; the server-side geocoding proxy is the most worthwhile fix.

## Sources
- https://operations.osmfoundation.org/policies/nominatim/
- https://wiki.openstreetmap.org/wiki/Nominatim
- https://github.com/komoot/photon
- https://github.com/maplibre/maplibre-gl-js
- https://developers.google.com/maps/billing-and-pricing/march-2025
- https://developers.google.com/maps/billing-and-pricing/faq
- https://developers.google.com/maps/ai/grounding-lite
- https://developers.google.com/maps/ai/grounding-lite/reference/mcp
- https://storerocket.io/learn/mapbox-pricing
- https://glama.ai/mcp/connectors/io.github.cyanheads/openstreetmap-mcp-server
