# 025. Purchase Orders and Procurement Workflow (Requisition, PO, Receiving, 3-Way Match)

## What it does
A procurement workflow covers the steps from "the site needs material" to "the supplier gets paid":
1. **Requisition**: a site lead requests materials or services against a project, cost code or BOQ position.
2. **Approval**: requests above a threshold go to an approver (office manager or owner).
3. **Purchase order (PO)**: the approved request becomes a numbered PO, sent to a vendor as a PDF or email.
4. **Receiving**: a delivery note or signed field ticket records what actually arrived, including partial deliveries.
5. **3-way match**: the vendor invoice is checked against the PO (price) and the receipt (quantity) before it is approved for payment. Anything outside tolerance is flagged as an exception.

This is the main way a small contractor catches overbilling, duplicate invoices and costs booked to the wrong job.

## Already in the codebase (with file paths)
- `backend/app/modules/procurement/models.py`: `PurchaseOrder`, `PurchaseOrderItem` (with `wbs_id` and `cost_category`), `GoodsReceipt` and `GoodsReceiptItem`.
- `backend/app/modules/procurement/service.py`: PO status machine (draft, issued, partially_received, completed, cancelled), `issue_po`, goods-receipt creation with quantity checks, and `confirm_goods_receipt`, which moves the PO to partially received or completed.
- `backend/app/modules/finance/models.py`: `Invoice` (incoming and outgoing, with retention), `InvoiceLineItem`, `Payment` and `ProjectBudget`.
- `backend/app/modules/rfq_bidding/`: RFQ and bid award. It depends on `oe_procurement`.
- `backend/app/core/workflow_engine.py`: generic approval steps and ball-in-court tracking.
- `frontend/src/features/procurement/ProcurementPage.tsx`: the procurement UI.

**Gap:**
- There is no `Requisition` entity and no PO approval step. `workflow_engine` exists but is not wired to POs.
- `Invoice` has no `po_id` or line-level link to PO or receipt lines, so no 3-way match or exception status is possible.
- There are no match tolerances (for example, ±2% price or ±0 quantity).
- There is no "create PO from BOQ positions or from an RFQ award" action.
- There is no vendor PO PDF or email dispatch.
- There is no committed-cost rollup (open PO value) into budget or EVM.
- There are no validation rules for procurement data.

## Who it helps and how much
- **Owner or office manager**: High value. One screen shows what was ordered, what arrived and what was billed. It stops overpayment and shows committed cost per job before invoices arrive.
- **Site foreman**: Medium value. A fast mobile requisition, plus a "confirm delivery" receipt with a photo of the delivery note.
- **Estimator**: Medium value. Buyout tracking: BOQ budget compared with PO value per position.
- **Bookkeeper**: High value, once invoices sync to accounting (QuickBooks or Xero) already matched.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Most of the PO and receipt base exists. The work touches `procurement`, `finance`, `boq` and `rfq_bidding`, plus `core/workflow_engine` and validation:
- Add `Requisition` and `RequisitionItem` models to `procurement`, with an approval workflow via `workflow_engine`, and a `convert_to_po` action.
- Add `po_id` to `finance.Invoice`, and `po_item_id`/`gr_item_id` to `InvoiceLineItem`.
- Add a `MatchService` that computes ordered, received and invoiced quantity and price per line. It sets the invoice `match_status` (matched, exception or overridden) using tolerances configured per tenant.
- Publish events (`procurement.po.issued`, `procurement.gr.confirmed`, `finance.invoice.matched`) through `core/events` so that `full_evm` and `costmodel` pick up committed and actual costs.
- Add validation rules, for example `procurement.invoice_exceeds_received_qty`, `procurement.price_variance_over_tolerance` and `procurement.duplicate_invoice_number`.
- Add `erp_chat/tools.py` tools: "list unmatched invoices" and "open POs for project X". Following the AI-suggests, human-confirms rule, these only suggest a match and a person approves it.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Odoo Purchase "bill control" and 3-way matching**: a reference design (received-quantities policy, "Should Be Paid" flag). Odoo Community is LGPL-3. Use it as a design reference only. https://www.odoo.com/documentation/17.0/applications/inventory_and_mrp/purchase/manage_deals/control_bills.html
- **invoice2data**: Python library that extracts fields from PDF invoices using templates. MIT, according to package registries (not checked against the LICENSE file). It needs pdftotext; scanned invoices need OCR first, for example OCRmyPDF. https://github.com/invoice-x/invoice2data
- **QuickBooks Online Accounting API**: has PurchaseOrder and Bill entities with `LinkedTxn`. Bill-to-PO linking must be set when the Bill is created. Intuit's docs are partly inconsistent on this, so test in a sandbox. Free developer sandbox. https://developer.intuit.com/app/developer/qbo/docs/workflows/manage-linked-transactions
- **Intuit QuickBooks Online MCP server**: official, early preview, runs locally over stdio with OAuth. Sources disagree on the license (Apache-2.0 or MIT). https://github.com/intuit/quickbooks-online-mcp-server
- **Xero Accounting API, PurchaseOrders endpoint**: OAuth 2.0 with a demo company. https://developer.xero.com/documentation/api/accounting/purchaseorders
- **Xero MCP server**: official, MIT. I could not confirm that it exposes purchase-order tools. https://github.com/XeroAPI/xero-mcp-server
- **Commercial comparison point**: ServiceTitan ships a configurable 3-way match setting for bills. It is proprietary and listed only as a feature benchmark. https://help.servicetitan.com/release-hub/docs/automatebill-reviews-with-3-way-match-to-save-time-and-reduce-errors

## Priority: 4/5 — the PO and receipt foundation exists, so linking invoices and adding requisitions with a match gives small contractors direct cost control for medium effort

## Sources
- https://www.odoo.com/documentation/17.0/applications/inventory_and_mrp/purchase/manage_deals/control_bills.html
- https://www.cybrosys.com/odoo/odoo-books/v17/purchase/3way-matching
- https://developer.intuit.com/app/developer/qbo/docs/workflows/manage-linked-transactions
- https://blogs.a.intuit.com/2019/08/19/new-entities-supported-in-linked-transactions
- https://github.com/intuit/quickbooks-online-mcp-server
- https://developer.xero.com/documentation/api/accounting/purchaseorders
- https://github.com/XeroAPI/xero-mcp-server
- https://github.com/invoice-x/invoice2data
- https://help.servicetitan.com/release-hub/docs/automatebill-reviews-with-3-way-match-to-save-time-and-reduce-errors
- https://www.getvergo.com/learn/three-way-matching-and-why-does-it-matter-for-construction-invoices
