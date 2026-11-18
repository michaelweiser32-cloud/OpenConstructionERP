# 027. Product catalogs and distributor APIs for materials

## What it does
Connects the estimating and procurement workflow to real manufacturer and distributor product data: searchable product records (article number, GTIN, description, unit, list/net price, classification, datasheets, BIM objects, EPD links), imported from standard catalog files or pulled from APIs. Estimators can attach a real product to a BOQ position or assembly component, refresh prices from a supplier price list, and pass the exact article numbers to an RFQ or purchase order.

## Already in the codebase (with file paths)
- `backend/app/modules/catalog/` (`oe_catalog`): `CatalogResource` model (`models.py`) with code, name, type, category, unit, base/min/max price, currency, region, `specifications` JSON, and `source` limited to `cwicr_extraction` / `manual`. The router (`router.py`) offers search, stats, CRUD, `POST /import/{region}` and `POST /extract/`, all built from the CWICR cost database. Nothing is supplier- or manufacturer-specific.
- `backend/app/modules/boq/epd_materials.py`: an embedded table of generic EPD/GWP values (OKOBAUDAT, ICE), not product-specific.
- `backend/app/modules/procurement/models.py`: purchase orders with `vendor_contact_id`, but no link to supplier article numbers or price lists.
- `backend/app/modules/bim_hub/exporters/cobie.py`: manufacturer fields appear only in COBie export.
- Gap: no import for supplier catalog formats (DATANORM, BMEcat, ETIM xChange), no supplier price-list versioning, no external product API connectors, and no GTIN or manufacturer article fields.

## Who it helps and how much
- **Small contractors and trades (DACH electrical, HVAC, plumbing):** high value. Wholesalers send DATANORM or BMEcat price lists as a matter of course, so importing them turns hours of retyping into minutes and keeps net prices current.
- **Small estimators in other regions:** medium value. Retail chains offer few official APIs. Commercial aggregators (1build in the US) cover pricing but cost money.
- **Design-and-build firms:** medium value. BIMobject and bSDD links tie BIM elements to real products and properties.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium**, for file-based import plus a connector interface. Live distributor APIs are Large and region-specific.
- Extend `oe_catalog` with `CatalogResource.source` values such as `datanorm`, `bmecat`, `etim_xchange` and `api:<provider>`, plus new fields: `supplier_contact_id` (linked to `contacts`), `manufacturer`, `article_no`, `gtin`, `price_valid_from`, and classification codes (ETIM, eCl@ss) in `specifications`.
- Add a `SupplierPriceList` model so every import is a version that can be compared with the last one.
- Add importers in `catalog/importers/`. Each runs through the validation pipeline as Import → Parse → VALIDATE → Store, using new rules in `validation/rules/` such as missing unit, zero price, duplicate article and currency mismatch.
- Define a `ProductSource` provider protocol so optional plugin modules (for example `oe_bimobject`, `oe_1build`, `oe_ec3`) can register through the hook registry without adding core dependencies.
- Emit a `catalog.price_list.imported` event. Assemblies and BOQ can subscribe to it and show "price changed" suggestions for a person to review, never auto-applied.
- Add an `erp_chat/tools.py` tool `search_products` so the AI assistant can search the catalog.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **`datanorm` (PyPI)**: Python reader for DATANORM 4. MIT, alpha, read-only. https://github.com/FahrJo/datanorm
- **BMEcat**: an XML standard. The only maintained parser found is .NET (BMECat.net). For Python, write a small parser with stdlib `xml.etree`. https://packages.nuget.org/packages/BMECat.net (library is described as open source)
- **ETIM classification and xChange (JSON)**: the model is under the Open Data Commons Attribution License, though national translations may be restricted to members. ETIM BMEcat 5.0 is announced as the last version, so prefer xChange. https://www.etim-international.com/classification/exchange-format/
- **2BA Product Data OpenAPI**: OpenAPI 3.1 specification based on ETIM xChange. https://product-data-openapi.2ba.nl/
- **buildingSMART Data Dictionary (bSDD)**: free REST API for classifications and properties, which a plain HTTP client can call. https://www.buildingsmart.org/?p=29545
- **BIMobject Developer API**: access requires an application and approval. It is mostly aimed at manufacturers and embedding; no public pricing or endpoints are published. https://developer.bimobject.com
- **EC3 / openEPD (Building Transparency)**: product-specific EPDs. API access is free for testing only; production use needs paid access and attribution. https://www.buildingtransparency.org/api-access-pricing/
- **1build**: US live material, labor and equipment pricing through a GraphQL API. Commercial, with tier prices not published. https://www.ycombinator.com/launches/IQo-1build-plaid-for-construction-cost-data
- **Retail (Home Depot, Lowe's)**: no official public product or pricing API was found. Lowe's partner APIs are restricted. The third-party scraper APIs are not recommended because of their terms-of-service risk.
- **MCP servers**: third-party hosted MCP connectors are listed for BIMobject (Vinkius) and ARCAT, along with Acelab Material Hub. Their licensing and maintenance are unverified, and there is no open-source MCP server for DATANORM, BMEcat or ETIM.

## Priority: 4/5 — supplier price-list import (DATANORM/BMEcat/ETIM) is cheap, standards-based and saves small firms real time; live APIs are optional plugins
Most small firms get prices from their wholesaler's catalog file, not from an API, and the existing `oe_catalog` module is the natural place to add this. BIMobject, EC3 and 1build are gated or paid, so they belong in optional modules.

## Sources
- https://developer.bimobject.com
- https://business.bimobject.com/developer-agreement
- https://github.com/FahrJo/datanorm
- https://pypi.org/project/datanorm/
- https://packages.nuget.org/packages/BMECat.net
- https://www.etim-international.com/classification/exchange-format/
- https://product-data-openapi.2ba.nl/
- https://www.buildingsmart.org/?p=29545
- https://pypi.org/project/bsdd/
- https://www.buildingtransparency.org/api-access-pricing/
- https://docs.buildingtransparency.org/ec3/api-and-integrations
- https://www.ycombinator.com/launches/IQo-1build-plaid-for-construction-cost-data
- https://www.projectsforce.com/post/lowe-s-api-explained-how-contractors-automate-orders-and-job-data
- https://vinkius.com/client/claude-code/connect/bimobject-mcp
- https://skillsplayground.com/mcps/comarcat-arcat/
