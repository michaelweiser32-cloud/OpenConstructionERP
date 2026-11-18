# 040. Multi-currency, VAT/sales tax and e-invoicing (XRechnung, ZUGFeRD/Factur-X, Peppol)

## What it does

This topic covers three layers that sit on top of the finance module:

1. **Multi-currency:** price, invoice and pay in several currencies. Exchange rates are snapshotted per document so totals stay reproducible.
2. **VAT/sales tax:** rates by country and by date, mixed rates on one invoice, tax-exempt lines, and construction-specific rules such as the German reverse charge for construction services (§13b UStG). Under the reverse charge the invoice shows no VAT and carries a mandatory note.
3. **Structured e-invoicing:** issue and receive invoices that comply with EN 16931:
   - XRechnung, the German UBL/CII XML format, mandatory for public clients.
   - ZUGFeRD/Factur-X, a PDF/A-3 file with embedded CII XML.
   - Peppol BIS Billing 3.0, sent through a Peppol Access Point.

In Germany every business has had to be able to *receive* e-invoices since 1 January 2025. Issuing becomes mandatory on 1 January 2027 for firms with more than EUR 800k turnover, and on 1 January 2028 for everyone else. A PDF sent by email will no longer count as a valid B2B invoice.

## Already in the codebase (with file paths)

- `backend/app/core/money.py` provides `MoneyValue` (Decimal amounts as strings, `convert()`, same-currency guards) and EN/DE number formatting.
- `backend/app/modules/i18n_foundation/models.py` holds `ExchangeRate`, `Country`, `WorkCalendar` and `TaxConfiguration` (country, `tax_code`, `rate_pct`, `tax_type`, effective_from/to, translations).
- `backend/app/modules/i18n_foundation/service.py` and `ecb_fetcher.py` provide `fetch_ecb_rates()`, exposed as `POST /exchange-rates/fetch-ecb` in `router.py`.
- `backend/app/modules/finance/models.py` has `Invoice`, with `currency_code`, `tax_amount`, `retention_amount` and `tax_config_id`. `Payment` stores an `exchange_rate_snapshot`. There is also `InvoiceLineItem`.
- `backend/app/modules/dach_pack/config.py` contains `tax_rules` (VAT types). The other regional packs (us_pack, uk_pack and so on) cover regional configuration.

**Gap:**

- There is no XRechnung, ZUGFeRD, Factur-X, Peppol or EN 16931 code anywhere in `backend/app` or `frontend/src`. A grep returned nothing.
- Nothing models the reverse charge, tax category codes per line (UNCL5305: S/Z/E/AE) or seller/buyer tax IDs.
- The incoming e-invoice inbox (parse an XML or PDF into an Invoice, then validate it) is missing.
- There are no validation rules for invoices, which the project principles require.

## Who it helps and how much

- **German and DACH small contractors and subcontractors:** High value. The law forces the change by 2027/2028, and public clients already reject anything that is not XRechnung.
- **EU firms in other countries:** Medium-High. Belgium's B2B Peppol mandate started in 2026, France's is phasing in, and Peppol is the common rail across these countries.
- **US/UK estimators:** Medium. Multi-currency and sales tax are useful for cross-border supply quotes, but e-invoicing is not mandatory for them yet.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)

**Medium** overall: about 2 to 3 weeks for generate, validate and receive. Peppol sending is extra and goes through a third-party Access Point.

The work splits into three modules:

- **New module `einvoice`** (manifest `depends=["oe_finance", "oe_contacts", "oe_i18n_foundation"]`):
  - `service.py` maps `Invoice` and `InvoiceLineItem` to the EN 16931 semantic model, then serializes it to CII (via drafthorse) or UBL (via a Jinja/lxml template).
  - It embeds the XML into the PDF report as PDF/A-3 with `factur-x`.
  - `router.py` exposes `GET /invoices/{id}/xrechnung.xml`, `/zugferd.pdf` and `POST /inbox` for parsing incoming files.
  - Events: it subscribes to `finance.invoice.approved` to auto-generate the files, and publishes `einvoice.received`.
- **Validation** (`backend/app/core/validation/rules/`):
  - A new `en16931` rule set that runs the XSD checks plus the Schematron business rules (BR-*).
  - An optional sidecar using the KoSIT validator, a Java container, as the authoritative check.
  - Results go into a ValidationReport (traffic-light) before the invoice can be sent.
- **Finance and i18n_foundation:**
  - Add per-line `tax_category` and an exemption reason.
  - Add a reverse-charge flag that is automatically suggested for construction subcontract invoices in DE, with human confirmation.
  - Add buyer reference (Leitweg-ID) and seller/buyer VAT IDs.
- **Peppol:** a pluggable connector in `integrations` that hands the UBL file to a certified Access Point over its REST API.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)

- **factur-x** (Akretion, Python): generates, extracts and XSD-checks Factur-X/ZUGFeRD PDFs. Licensed BSD-style; one listing says "Non-SPDX", so check the LICENSE file. https://github.com/akretion/factur-x
- **python-drafthorse** (pretix): generates and parses the ZUGFeRD 2.3 / CII XML model. Apache-2.0 (bundled FeRD schemas are under their own terms). https://github.com/pretix/python-drafthorse
- **KoSIT validator** plus **validator-configuration-xrechnung**: the official XRechnung and EN 16931 validation. Java, Apache-2.0. https://github.com/itplr-kosit/validator
- **Mustangproject**: Java library, validator and CLI for ZUGFeRD/Factur-X/XRechnung. Apache-2.0. https://github.com/ZUGFeRD/mustangproject
- **ECB reference rates**: already integrated. Free.
- **Peppol Access Points with APIs**: these are commercial. Qvalia publishes plans from roughly EUR 9 to 899 per month, with the API from its mid tier. Others (Digiteal, Dokapi) do not publish prices. No free open-source Access Point is viable for production.
- **MCP servers (early, not vetted):**
  - InvoiceXML MCP (MIT, hosted plus self-host).
  - `e-invoice-mcp` from Fintom8 (MIT, but it proxies to a hosted API).
  - The `mcp-einvoicing-*` family (Belgium, Germany, France, Italy), which has very low adoption.

  None is mature enough to depend on; expose our own `einvoice` tools via `erp_chat/tools.py` instead.

## Priority: 5/5 — legally mandated in Germany (issue by 2027/2028, receive since 2025) with a clear gap on top of existing finance/tax/currency foundations and mature Apache/BSD building blocks.

## Sources

- https://www.avalara.com/us/en/vatlive/country-guides/europe/germany/german-e-invoicing.html
- https://www.truecommerce.com/en-gb/blog/e-invoicing-germany-timeline-deadlines/
- https://docs.invopop.com/compliance/germany
- https://e-rechnung-bund.de/en/e-invoicing-for-software-companies/
- https://github.com/itplr-kosit/validator
- https://github.com/itplr-kosit/validator-configuration-xrechnung
- https://github.com/ZUGFeRD/mustangproject
- https://github.com/pretix/python-drafthorse
- https://akretion.com/en/blog/akretion-publishes-an-opensource-factur-x-python-library
- https://qvalia.com/pricing/enterprise/
- https://doc.digiteal.eu/docs/peppol-access-point
- https://pypi.org/project/e-invoice-mcp/
- https://pypi.org/project/mcp-einvoicing-be
- https://www.gesetze-im-internet.de/ustg_1980/__13b.html
