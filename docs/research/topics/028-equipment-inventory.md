# 028. Equipment, tool and inventory/yard tracking (QR/barcode, utilization, maintenance)

## What it does
An asset register for company-owned plant, small tools and yard stock. Each item gets a QR/barcode label, and anyone with a phone can scan it to check it out to a person or project, check it back in to the yard, or move it between jobs. On top of that come utilization (hours used vs. available, idle vs. operating), preventive maintenance (service by hours, km or date, inspection and certification expiry such as lifting gear or PAT tests), and simple stock levels for consumables. For larger machines, usage hours can come straight from OEM telematics through the ISO 15143-3 (AEMP 2.0) standard instead of being typed in. The commercial payoff is internal equipment charge-out: a machine assigned to a project costs that job its internal rate, which feeds job costing and makes the next estimate's equipment rates more accurate.

## Already in the codebase (with file paths)
- `backend/app/modules/catalog/models.py` and `catalog/manifest.py`: a catalog resource with `resource_type` set to equipment, material, labor or operator. These are rate entries, not physical serialised assets.
- `backend/app/modules/fieldreports/models.py`: `SiteEquipmentLog` (`oe_fieldreports_equipment`) records operational, standby and breakdown hours per daily report. `equipment_description` is free text with no foreign key to an asset, so hours cannot be rolled up per machine.
- `backend/app/modules/costs` and `assemblies` hold equipment cost components for estimating.
- **Gaps:** there is no asset/tool register, no QR or barcode generation or scanning (the frontend and `package.json` have no scanner library), no check-in/out custody log, no yard or stock locations, no maintenance schedules or work orders, no utilization reports, no telematics import, and no equipment charge-out into job costing (see 020).

## Who it helps and how much
Small general contractors and trade subcontractors with roughly 20 to 500 tools and a few machines. Tools that walk off site, rentals that run on after the work is done, and missed services are a steady, invisible cost. Dedicated tools (ShareMyToolbox, GoCodes, Hilti ON!Track, ToolWatch) mostly sell on quote or a monthly subscription, so a built-in register is a real saving. Value is **Medium to High**: it matters a lot to firms that own equipment and very little to pure estimating offices.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium** for a new `oe_equipment` module (depends on `oe_projects`, `oe_catalog`, `oe_contacts`). Telematics adds another Small to Medium on top.
- `models.py`: `Asset` (tag code, serial, category, `catalog_resource_id`, internal rate per hour/day, status, current location/project/holder), `AssetMovement` (check-out/in or transfer, from, to, by whom, when, meter reading, photo), `Location` (yard, site, van), `MaintenancePlan` (interval in hours, km or days) and `MaintenanceEvent`, `StockItem` with min level.
- `router.py`: `/scan/{tag}` resolves a label to an action screen, plus bulk label PDF export (QR via segno, rendered with the existing reporting/PDF stack).
- Frontend `features/equipment`: a mobile-first scan page built on html5-qrcode / @zxing/browser, with manual tag entry as a fallback.
- Events: publish `equipment.checked_out` and `equipment.hours_logged`. `costmodel`/`finance` subscribe to post internal charge-out as actual cost. Add an `asset_id` foreign key on `SiteEquipmentLog` so daily report hours update meters.
- Validation rules (`validators.py`): asset on two projects at once, maintenance overdue, inspection certificate expired, asset checked out longer than N days.
- `erp_chat/tools.py`: "where is asset X", "what is due for service this week".
- Optional `integrations/aemp`: poll ISO 15143-3 endpoints (Deere, Cat, Volvo CE, Trackunit) for cumulative operating hours and location.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **segno**, a pure-Python QR generator, BSD-3-Clause: https://pypi.org/project/segno/
- **html5-qrcode**, a browser camera scanner, Apache-2.0: https://github.com/mebjas/html5-qrcode
- **@zxing/browser / @zxing/library**, a multi-format barcode decoder (browser package listed as MIT; check the core library's LICENSE): https://github.com/zxing-js/browser
- **Snipe-IT**, an open-source asset manager with check-in/out and a JSON REST API, AGPL-3.0. It is a reference design or optional sync target, not a dependency: https://github.com/grokability/snipe-it
- **Snipe-IT MCP servers** (community, unofficial): https://github.com/jameshgordy/snipeit-mcp and https://github.com/mguttmann/the-real-snipeit-mcp. I did not verify their licenses or maintenance.
- **ISO 15143-3 / AEMP 2.0 telematics APIs**: free for machine owners, but access needs an OEM account or subscription. Deere https://developer.deere.com/dev-docs/aemp, Trackunit https://developers.trackunit.com/docs/api-reference/aemp-iso-api/aemp-iso-api/, Volvo CE https://developer.volvoce.com/vce/cs/node/79
- I found no dedicated MCP server for construction tool-tracking SaaS (ShareMyToolbox, Hilti ON!Track, ToolWatch). Their pricing is mostly by quote.

## Priority: 3/5 — clear money-saver for equipment-owning small contractors, and cheap to build with open libraries, but outside the estimating core
For estimating-only users it is secondary to BOQ, costs and job costing. Its biggest leverage is feeding real equipment hours and charge-out into job costing.

## Sources
- https://github.com/grokability/snipe-it
- https://github.com/mebjas/html5-qrcode
- https://github.com/zxing-js/browser
- https://pypi.org/project/segno/
- https://developer.deere.com/dev-docs/aemp
- https://developers.trackunit.com/docs/api-reference/aemp-iso-api/aemp-iso-api/
- https://developer.volvoce.com/vce/cs/node/79
- https://gomotive.com/blog/aemp-heavy-equipment-telematics/
- https://gocodes.com/small-tool-tracking-software/
- https://toolradar.com/tools/toolwatch/pricing
- https://glama.ai/mcp/servers/@Wil-Collier/snipeit-mcp
