# 026. Material takeoff to supplier quote request (RFQ) automation

## What it does
Turns the materials in a takeoff or BOQ into a priced request to suppliers in a few clicks. The flow: aggregate material quantities from the takeoff or BOQ resources, group them by trade or supplier category, apply waste factors and order units (m3 of concrete, sheets of board, pieces of lumber), and generate one RFQ per supplier group with line items. The RFQ goes out by email as PDF/CSV/XLSX or through a supplier link. Supplier replies (often PDF quotes) are parsed back into line-level prices, compared side by side, and the winner is turned into a purchase order. Commercial tools in this space include Field Materials, DigiBuild DigiProcure and Buildxact's supplier RFQ feature. They all market roughly the same loop: takeoff, then RFQ, then quote leveling, then PO.

## Already in the codebase (with file paths)
- `backend/app/modules/rfq_bidding/` (models.py, service.py): an `RFQ` holds a free-text `scope_of_work`, `issued_to_contacts` and a status workflow (create, issue, submit_bid, evaluate_bid, award_bid). **There are no RFQ line items.** `RFQBid.bid_amount` is a single lump sum, so line-level quote comparison is impossible today.
- `backend/app/modules/boq/router.py` (`GET /boqs/{boq_id}/resource-summary/`) and `boq/service.py` (`_normalize_resource_category`): these already aggregate position `metadata.resources` into labor/material/equipment/subcontractor categories. This is the natural source for a material list.
- `backend/app/modules/takeoff/models.py` (`TakeoffMeasurement` with `group_name`, `type`) and `dwg_takeoff/`: measured quantities, grouped but not linked to supplier categories.
- `backend/app/modules/procurement/models.py`: `PurchaseOrder` and `PurchaseOrderItem` have line items (qty, unit, unit_rate, wbs_id), which makes them a ready target for "award to PO".
- `backend/app/modules/tendering/` handles subcontractor bid packages (`TenderPackage`/`TenderBid`). It overlaps, but the target is subcontractors, not material suppliers.
- `backend/app/modules/integrations/email_service.py` (`send_email`) and `contacts/` cover outbound delivery and the supplier list.

**Gap:** there is no bridge from takeoff or resource-summary to RFQ, no RFQ line items, no waste or order-unit conversion, no supplier categories on contacts, no quote intake or parsing, no line-level leveling, and no RFQ-to-PO conversion.

## Who it helps and how much
Small general contractors, builders, and trade contractors (framing, drywall, concrete, MEP) that buy materials themselves. Today they retype takeoff totals into emails or spreadsheets for 2-5 suppliers per package and then compare PDFs by hand. Automating this saves hours per bid and makes it practical to ask more suppliers. Vendors claim 5-10% material savings (self-reported, unverified). The value is **High**, because it connects modules the ERP already has into a workflow that pays off on every job.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Mostly extends `rfq_bidding`, with no new module needed:
1. Add `RFQItem` (description, qty, unit, waste_pct, order_unit, source_ref to a BOQ position, resource or takeoff measurement) and `RFQBidItem` (unit_price, alternate, lead_time). Each comes with an Alembic migration.
2. Add a service `build_rfq_from_boq(boq_id, category_filter, supplier_ids)` that calls the BOQ resource-summary logic. It emits an `rfq.created_from_takeoff` event on the core event bus.
3. Generate the export (CSV/XLSX via openpyxl, PDF via the existing reporting stack) and send it through `integrations/email_service.py`, optionally with a tokenized supplier link where suppliers type in prices.
4. Quote intake: upload a supplier PDF, extract tables with pdfplumber, and have the AI module suggest line matches with confidence scores. The user confirms every match, per the "AI-augmented, human-confirmed" rule.
5. Leveling grid in `frontend/src/features` (rfq) and an "Award to PO" action that creates `procurement` PurchaseOrderItems.
6. Validation rules (`rfq_quality`): items with zero quantity, missing units, RFQs with fewer than 2 suppliers, quote totals that deviate from the BOQ material budget.
7. erp_chat tool: "create RFQ for concrete from BOQ X".

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **pdfplumber**, for extracting quote tables from supplier PDFs: https://github.com/jsvine/pdfplumber (MIT).
- **Camelot**, an alternative table extractor: https://github.com/camelot-dev/camelot (MIT).
- **openpyxl**, for XLSX RFQ export and import: https://openpyxl.readthedocs.io (MIT).
- **IMAP/email MCP servers**, community projects for reading quote replies and attachments, for example https://github.com/tonykipkemboi/gmail-imap-mcp and https://github.com/emadmokhtar/email-mcp-go. Licenses vary per repo, and maturity has not been verified. I found no official supplier-RFQ MCP server.
- **Datanorm / BMEcat** (DACH supplier price-list formats) could be imported into `costs` for pre-pricing: https://www.anglera.com/glossary/datanorm (glossary; the official spec is distributed by vendors).
- **Reference designs**: the Odoo Community Purchase RFQ flow. Most Odoo vendor-portal add-ons are proprietary (OPL-1): https://apps.odoo.com/apps/modules/18.0/ais_rfq_vendor_portal
- **Public supplier pricing APIs** (big-box lumber and building merchants): I could not verify any public, free API. Supplier pricing has to come through email/CSV round trips or a supplier portal.

## Priority: 5/5 — high-frequency, money-saving workflow that mostly connects existing modules (BOQ resources, rfq_bidding, procurement, email) instead of building new ones.

## Sources
- https://digibuild.com/products/digiprocure/
- https://fieldmaterials.com/platform/quotes
- https://stg1.buildxact.com/us/?p=9277
- https://www.ruh.ai/industrial/construction/suppliers
- https://github.com/jsvine/pdfplumber
- https://github.com/tonykipkemboi/gmail-imap-mcp
- https://github.com/emadmokhtar/email-mcp-go
- https://apps.odoo.com/apps/modules/18.0/ais_rfq_vendor_portal
- https://www.anglera.com/glossary/datanorm
