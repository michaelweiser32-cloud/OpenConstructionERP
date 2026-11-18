# 030. Vendor / Supplier Database (ratings, trades, regions, performance history)

## What it does
A single searchable register of subcontractors and suppliers that answers "who can do drywall in this region, is their insurance valid, and how did they do last time?" Core pieces:
- **Trade/scope tags** keyed to the classification systems already in use (DIN 276 cost groups, MasterFormat divisions, NRM elements, or free tags).
- **Service regions** (country, postal-code prefixes or radius) so tender invitations go to subs who actually work in the project area.
- **Ratings and performance history**: per-project scorecards (quality, schedule, safety, communication, price competitiveness) plus figures pulled from existing modules: bid hit rate, bid-vs-award spread, change-order and NCR/punch counts, late deliveries on goods receipts.
- **Compliance expiry**: insurance and certificate expiry, prequalification status, and reminders.
- **Shortlist generation** for tender packages and RFQs ("top 5 drywall subs within 50 km, prequalified, rating >= 3.5").

## Already in the codebase (with file paths)
- `backend/app/modules/contacts/models.py`: `Contact` with `contact_type` (`client|subcontractor|supplier|consultant|internal`), `company_name`, `vat_number`, `country_code`, `address` (JSON), `certifications` and `insurance` (JSON lists), `prequalification_status`, `qualified_until`, `payment_terms_days`, `currency_code`, `metadata_`. This is a solid base for a vendor master.
- `frontend/src/features/contacts/ContactsPage.tsx`: CRUD UI.
- `backend/app/modules/procurement/models.py`: `PurchaseOrder.vendor_contact_id` and `GoodsReceipt`, the source for delivery-performance data.
- `backend/app/modules/rfq_bidding/models.py`: bids carry `technical_score` / `commercial_score`.
- `backend/app/modules/tendering/models.py`: `TenderBid` stores a free-text `company_name`/`contact_email` and **no FK to Contact**, so bid history cannot be tied to a vendor record.

**Gap:** there are no structured trades, no service regions, no rating or scorecard tables, no aggregated performance view, no expiry alerts and no shortlist query. Tender bids are not linked to vendors.

## Who it helps and how much
Small GCs and estimating firms usually keep their sub list in spreadsheets or in someone's head. A trade- and region-filtered list with past performance cuts the time spent inviting bidders, lowers the risk of hiring a poor or uninsured sub, and keeps the knowledge when staff leave. Value is **High**: the feature is used on every tender and PO. Dedicated prequalification tools are priced for larger firms (mostly "contact sales" or per-vendor pricing; one vendor lists sub management at about $4.8k/year for 20 profiles), so a built-in register is a real differentiator.

## Implementation effort
**Medium.** It extends `contacts` and touches `tendering`, `rfq_bidding`, `procurement` and `notifications`. There is no need for a new module, though a `vendor_performance` sub-package keeps the code tidy.
1. Models: `VendorTrade` (contact_id, classification standard + code), `VendorRegion` (country, postal prefix or lat/lon + radius), `VendorEvaluation` (contact_id, project_id, criteria scores JSON, comment, evaluator). Alembic migration.
2. Add a nullable `contact_id` FK to `TenderBid` and backfill it by matching email or VAT number.
3. Event handlers via `app/core/events.py`: on `tender.awarded`, `po.received`, `ncr.created` and `changeorder.approved`, update cached KPIs in `Contact.metadata_` (or a `VendorStats` table).
4. Validation rules: `vendor.insurance_expired` and `vendor.not_prequalified` (warn when such a vendor is invited or a PO is issued to them), and `vendor.duplicate` (fuzzy match on name or VAT).
5. Endpoint `GET /api/v1/contacts/vendors/shortlist?trade=&region=&min_rating=`, plus an `erp_chat` tool ("find 3 roofers near the project").
6. Daily expiry reminders through `notifications`. All labels go through i18n.

## Building blocks
- **EU VIES VAT check REST API**: `https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number`. Free, official EC service. The swagger is linked in community SDKs; the no-key behaviour is reported by third parties, so verify it. https://github.com/rocketfellows/vies-vat-validation-php-sdk-rest
- **SAM.gov Entity Management + Exclusions APIs** (US): free public API key; returns UEI, NAICS and debarment status. https://open.gsa.gov/api/entity-api/
- **UK Companies House API**: free with a registered key; gives company status and officers. https://developer.company-information.service.gov.uk/
- **OpenCorporates API**: global company registries; paid plans (pricing is sales-led), free only for transparency/public-benefit uses. https://opencorporates.com/pricing/
- **GLEIF LEI API**: free and open. Few small subs have an LEI, so it is low relevance. A community MIT-licensed MCP server exists (not official): https://mcp.so/servers/gleif-mcp-server
- **RapidFuzz** (MIT): fuzzy duplicate detection on vendor names. https://github.com/rapidfuzz/RapidFuzz
- **PostGIS / plain haversine**: radius search. PostGIS is optional; the core can use postal prefixes so that SQLite still works.
- **MCP:** I could not find any official vendor-management or prequalification MCP server. Third-party VIES MCP servers exist on aggregators (e.g. glama.ai) but are unvetted.

## Priority: 4/5. High daily value for tendering and procurement, and it builds on the existing `contacts` model with medium effort and free public APIs.

## Sources
- https://open.gsa.gov/api/entity-api/
- https://developer.company-information.service.gov.uk/
- https://opencorporates.com/pricing/
- https://github.com/rocketfellows/vies-vat-validation-php-sdk-rest
- https://mcp.so/servers/gleif-mcp-server
- https://github.com/rapidfuzz/RapidFuzz
- https://safetyculture.com/app/contractor-prequalification-software/
- https://projul.com/blog/subcontractor-management-software/
- https://www.capterra.com/p/201807/DocuQual/
