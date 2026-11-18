# 035. Invoice OCR and Accounts-Payable Automation

## What it does
Supplier invoices arrive as PDFs, phone photos, email attachments, or (more and more in the EU) as structured e-invoices: XRechnung, or ZUGFeRD/Factur-X, which is a PDF with embedded XML. AP automation:
1. **Captures** the invoice from an upload, a forwarding mailbox, or the mobile camera.
2. **Extracts** the header fields (supplier, invoice number, dates, net/VAT/gross, retention, PO reference) and the line items.
3. **Matches** the invoice to the purchase order and goods receipt (2-/3-way match).
4. **Codes** each line to a project, WBS or cost code, and suggests the code with a confidence score.
5. **Routes** it for approval, then feeds job costing and budget-vs-actual. It can also export to the accounting system.

For a small contractor, most of the value is in step 4: cost-coding every bill to a job by hand is slow and error-prone.

## Already in the codebase (with file paths)
- `backend/app/modules/finance/models.py`: `Invoice` (payable/receivable, subtotal/tax/retention/total, `status`, `metadata` JSON) and `InvoiceLineItem` with `wbs_id` and `cost_category`. This is the target data model for coding.
- `backend/app/modules/finance/router.py`: CRUD, Excel export, and `POST /{invoice_id}/approve/`. Approval is a single step, from draft/submitted to approved.
- `backend/app/modules/procurement/router.py` (`/{po_id}/create-invoice/`): creates a draft payable invoice from a PO. `procurement/models.py` has `PurchaseOrder` and `GoodsReceipt`, which provide the inputs for 3-way matching.
- `backend/app/modules/ai/router.py`: file upload with AI Vision OCR for images and PDF text extraction. Today this is aimed at BOQ generation only.
- `backend/app/modules/documents/service.py`: PDF handling. It explicitly does not run external OCR.
- `backend/app/modules/integrations/email_service.py`: email plumbing that an inbound "bills@" mailbox could reuse.
- **Gap:** there is no invoice-field extraction, no e-invoice (XRechnung/ZUGFeRD) parser, no PO/GR matching logic, no AI cost-code suggestion, no duplicate-invoice check, and no AP validation rules.

## Who it helps and how much
- **Owner or bookkeeper at a 5–30 person contractor:** saves an estimated 2–5 minutes per invoice of keying and coding (my estimate, not a measured figure). Job cost actuals become current instead of a month behind.
- **Project managers:** see committed vs. invoiced vs. paid per cost code in real time, because the data feeds `full_evm` and the budget views.
- **DACH firms:** every German business has had to be able to *receive* EN 16931 e-invoices since 1 Jan 2025. Issuing becomes mandatory in phases in 2027/2028. Parsing XRechnung/ZUGFeRD is therefore a compliance need, and it is also the cheapest "OCR": the data is already structured, so nothing needs recognising.

Value: High.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** The work is a new module `oe_ap_capture` with `depends=["oe_finance", "oe_procurement", "oe_documents", "oe_ai"]`.
- **Intake:** an upload endpoint plus an email-ingest hook from `integrations`. Files are stored via `core/storage`.
- **Extraction pipeline:**
  1. Embedded XML (ZUGFeRD/Factur-X) or pure XML (XRechnung): deterministic parse.
  2. Digital PDF: text layer plus invoice2data templates per recurring supplier.
  3. Scans/photos: Docling, PaddleOCR or docTR, then LLM field extraction through the existing `ai` module. A pluggable cloud provider (Mindee, Veryfi) is optional.
- **Output:** a draft `Invoice` with per-field confidence values in `metadata`. It is never posted automatically, which follows the "AI-augmented, human-confirmed" principle.
- **Coding suggestion:** use the PO line's WBS when the invoice matches a PO. Otherwise use the supplier's coding history, then vector similarity via `core/vector`.
- **Validation rule set `ap_quality`:**
  - duplicate check (supplier + number + amount)
  - net + VAT = gross
  - PO/GR quantity and price tolerance
  - missing cost code
  - VAT ID format
- **Events:** emits `ap.invoice.captured` and `ap.invoice.coded` events for workflows and notifications.
- **Frontend:** a split-view review screen with the document on the left and the editable fields on the right.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **invoice2data** (MIT): YAML/regex templates per supplier. It can use tesseract, docTR or PaddleOCR as the OCR backend. https://github.com/invoice-x/invoice2data
- **Docling** (MIT code; model licenses vary): layout, tables and OCR for PDFs and images. Ships an MCP server. https://github.com/docling-project/docling
- **PaddleOCR** (Apache-2.0): already the planned OCR stack in CLAUDE.md. https://github.com/PaddlePaddle/PaddleOCR
- **docTR** (Apache-2.0): deep-learning OCR. https://github.com/mindee/doctr
- **factur-x** (Akretion): extracts and generates Factur-X/ZUGFeRD XML. https://github.com/akretion/factur-x
- **drafthorse:** low-level ZUGFeRD XML parse and generate. https://pypi.org/project/drafthorse/
- **PyCheval:** parses ZUGFeRD/Factur-X. Early-stage, and it does not support XRechnung or the Extended profile yet. https://github.com/zfutura/pycheval
- **Mindee** (commercial; usage-based, trial available, I could not verify per-page list prices): https://www.mindee.com/pricing
- **Veryfi** (commercial): has a community MCP listing, which I have not verified as official. https://mcp.so/servers/mcp-server-veryfi
- **MCP servers for Mindee:** I only found third-party wrappers (for example a Glama-listed connector). I found no official Mindee MCP server.
- **Accounting push:**
  - QuickBooks Online Bill + Attachable API: https://developer.intuit.com/app/developer/qbo/docs/workflows/attach-images-and-notes
  - Xero Accounting API, where invoices of type ACCPAY are bills: https://developer.xero.com/documentation/api/accounting/invoices

## Priority: 4/5 — AP coding feeds job costing and is now an EU compliance need; the data model exists, so the gap is extraction, matching and coding, all built from open-source parts.

## Sources
- https://invoice2data.readthedocs.io/latest/faq.html
- https://github.com/invoice-x/invoice2data
- https://github.com/docling-project/docling
- https://github.com/akretion/factur-x
- https://pypi.org/project/PyCheval/
- https://pypi.org/project/drafthorse/
- https://www.mindee.com/pricing
- https://mcp.so/servers/mcp-server-veryfi
- https://glama.ai/mcp/connectors/io.usefulapi/mindee
- https://developer.intuit.com/app/developer/qbo/docs/workflows/attach-images-and-notes
- https://developer.xero.com/documentation/api/accounting/invoices
- https://docs.invopop.com/compliance/germany
- https://ec.europa.eu/digital-building-blocks/sites/spaces/einvoicingCFS/pages/718735697/2024+Germany+2024+eInvoicing+Country+Sheet
