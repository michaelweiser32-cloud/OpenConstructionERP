# 087. Insurance certificate (COI / ACORD 25) tracking and expiry alerts

## What it does
A GC or estimator asks every subcontractor and vendor for a Certificate of Insurance. In the US this is usually the ACORD 25 (Certificate of Liability Insurance). COI tracking covers four jobs:
- Store each certificate as a document with structured fields: insurer, policy number, coverage type (GL, auto, umbrella, workers comp), per-occurrence and aggregate limits, effective and expiry dates, and whether additional insured or waiver of subrogation is ticked.
- Check those fields against the project's or contract's insurance requirements, for example GL of at least 1M per occurrence.
- Send alerts before expiry, typically at 30, 14 and 0 days, to the internal owner and to the sub.
- Optionally block a sub from being awarded or paid while it is non-compliant.

UK and EU equivalents are an insurance schedule or broker letter; the data model is the same, without the ACORD layout.

## Already in the codebase (with file paths)
- `backend/app/modules/contacts/models.py`: `Contact.insurance` and `Contact.certifications` are free-form JSON lists, and there is a `prequalification_status` string.
- `backend/app/modules/contacts/schemas.py`: `insurance: list[Any]` has no schema. The status pattern is `pending|approved|rejected|expired`, and there is a `with_expiring_prequalification` counter in the stats schema.
- `backend/app/modules/contacts/service.py`: only passes `insurance` through; nothing is computed or checked.
- Infrastructure that can be reused: `backend/app/modules/notifications/`, `backend/app/core/events.py`, `backend/app/core/storage.py`, `backend/app/modules/documents/`, `backend/app/modules/integrations/` (email, Slack, Teams), and `backend/app/core/validation/`.

**Gap:** there is no typed policy or coverage model, no link from a COI to a stored PDF, no requirement templates, no expiry scheduler or alerts, no compliance rule, and no extraction from uploaded certificates.

## Who it helps and how much
- **High for small US GCs and specialty contractors.** A lapsed sub policy can pass claims to the GC. Most small firms track COIs in spreadsheets today, and the commercial tools charge per vendor:
  - TrustLayer has a free starter tier for a small vendor count.
  - BCS lists about $0.95 per vendor per month.
  - myCOI and Jones are quote-based enterprise tools (third-party comparisons; verify with the vendor).
- **Medium for UK and EU users.** The same expiry tracking applies to insurance schedules and to certifications such as CSCS or trade licences.
- Estimators benefit indirectly: bid leveling in `rfq_bidding` and `tendering` can flag subs that are not compliant.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Overall: Medium.** About 60% of the work is Small: typed model, expiry job and alerts.
1. **Data model.** Add `InsurancePolicy` (contact_id, document_id, coverage_type, insurer, policy_no, limits as JSON, effective/expiry dates, additional_insured, waiver_of_subrogation, source, confidence). Add `InsuranceRequirement` templates per project or contract. This can sit inside `contacts`, or in a new `oe_compliance` module that depends on `oe_contacts`, `oe_documents` and `oe_notifications`.
2. **Validation rules.** Register `coi.expired`, `coi.expiring_soon`, `coi.limit_below_requirement` and `coi.missing_additional_insured` in the validation engine, so status feeds the existing traffic-light UI.
3. **Expiry job.** Run a daily check (in-process for dev, Celery beat in prod). It publishes events such as `compliance.coi.expiring`. The `notifications` module and the email, Slack and Teams integrations subscribe to them. A templated email asks the sub for a renewed COI.
4. **Extraction (optional, AI-augmented).**
   - Fillable PDFs: read the form fields with pypdf.
   - Scanned PDFs: run OCR with PaddleOCR, which is already in the planned stack, or have the `ai` module produce structured LLM output.
   - In both cases, show confidence scores and require human confirmation, per project principle 7.
5. **Hooks.** A filter hook on award or payment actions in `procurement`, `rfq_bidding` and `finance` warns or blocks when a sub is non-compliant.
6. **erp_chat tool.** Add a `list_expiring_certificates` tool to `backend/app/modules/erp_chat/tools.py`.

**Licensing caveat:** ACORD forms are copyrighted. ACORD's licence terms restrict embedding the forms in software, and vendors cannot sublicense them. The safe scope is to parse certificates that users upload, and never to generate or reproduce the ACORD 25 layout.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **pypdf** (https://github.com/py-pdf/pypdf, BSD-3): AcroForm field extraction from fillable ACORD PDFs.
- **PaddleOCR** (https://github.com/PaddlePaddle/PaddleOCR, Apache-2.0): OCR for scanned certificates.
- **UiPath ACORD25 ML package docs** (https://docs.uipath.com/document-understanding/automation-cloud/latest/user-guide/acord25-ml-package): a public field list that is a useful reference for the schema. The product itself is commercial.
- **Commercial extraction APIs**, an optional paid fallback: Sensible (https://www.sensible.so/blog/extracting-data-from-certificates-of-insurance) and Extend (https://www.extend.ai/resources/acord-form-data-extraction-api).
- **MCP:**
  - I found no widely adopted open-source MCP server for COI tracking.
  - CSOAI-ORG/acord-bridge-mcp (https://github.com/CSOAI-ORG/acord-bridge-mcp) parses and validates ACORD messages. Its maturity is unverified, and it is aimed at AI-governance use, not COI tracking.
  - A commercial brokerage MCP (https://portal.delegancebrokerage.com/docs/mcp) advertises COI generation and requires an account.
  - Recommendation: build this natively, and optionally expose it through erp_chat tools.

## Priority: 4/5 — cheap to build on existing contacts, notifications and validation, high risk-reduction value for US small GCs, and replaces a per-vendor SaaS fee
## Sources
- https://www.acord.org/forms-pages/acord-forms/forms-faq
- https://www.acord.org/docs/default-source/forms/advantagenotice.pdf?sfvrsn=180dbf0_16
- https://docs.uipath.com/document-understanding/automation-cloud/latest/user-guide/acord25-ml-package
- https://www.sensible.so/blog/extracting-data-from-certificates-of-insurance
- https://www.nutrient.io/blog/insurance-document-extraction/
- https://subdoc.io/blog/affordable-coi-tracking-software
- https://www.vertikalrms.com/article/best-coi-tracking-software-2026-top-coi-platforms-for-contractors/
- https://github.com/CSOAI-ORG/acord-bridge-mcp
- https://portal.delegancebrokerage.com/docs/mcp
- https://github.com/py-pdf/pypdf
- https://github.com/PaddlePaddle/PaddleOCR
