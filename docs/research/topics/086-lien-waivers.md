# 086. Lien waivers and preliminary notices (conditional/unconditional, state forms, Levelset)

## What it does
In US construction, unpaid contractors, subs and suppliers can file mechanics liens against the property. Two documents control that risk:
- **Preliminary notices** (California 20-day notice, Florida Notice to Owner, Texas monthly notices, and others). Many states require them before a lien right exists, and each state sets its own deadlines and forms.
- **Lien waivers/releases** are exchanged with each payment. There are four kinds: conditional or unconditional, each for a progress or a final payment. Some states require statutory wording. In California a waiver must substantially follow Civil Code §§8132/8134/8136/8138 to be effective. Arizona (§33-1008), Georgia (§44-14-366) and Texas also prescribe forms. Florida (§713.20) offers optional forms. Most states do not regulate waivers.

A module would generate the right form for the project state and payment type, track waiver status for each invoice or payment, block or flag payments that lack a waiver, and calculate notice and lien deadlines.

## Already in the codebase (with file paths)
- Nothing specific to liens. A grep for `lien|waiver|preliminary notice|levelset` in `backend/app` finds no relevant code.
- Related building blocks:
  - `backend/app/modules/finance/models.py`: `Invoice` (with `retention_amount`) and `Payment` are the natural link points.
  - `backend/app/modules/us_pack/config.py`: AIA G702 pay-app fields, including `retainage` and `total_earned_less_retainage`. No state-level legal data.
  - `backend/app/modules/contacts/`: subs and suppliers who would sign waivers.
  - `backend/app/modules/documents/` and `cde/`: storage for signed PDFs.
  - `reportlab` (in `backend/pyproject.toml`): PDF generation.
- Gap: a waiver/notice model, state form templates, a deadline calendar and a "no waiver, no payment" check.

## Who it helps and how much
- **US subcontractors and suppliers:** high value. A missed preliminary notice can forfeit lien rights, so deadline reminders protect receivables.
- **Small US GCs:** high value. They collect waivers from subs before releasing draws, and lenders and title companies require them.
- **Non-US users:** none. This feature is US-only and should live in `us_pack` or its own optional module.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** New optional module `oe_lien_waivers` with `depends=["oe_finance", "oe_contacts", "oe_us_pack"]`.
- `models.py`:
  - `LienWaiver`: type, payment kind (progress/final), amount, through-date, `invoice_id`/`payment_id`, status (requested/signed/received), and a document link.
  - `PreliminaryNotice`: project, recipient, due date, served date.
- `state_rules/*.json`: state data such as which form is statutory, notice-day offsets and lien-filing windows. Keep the data versioned and add a "not legal advice" disclaimer. Start with CA, TX, FL, AZ and GA, and use a generic form elsewhere.
- `service.py`: render PDFs with reportlab, using form templates with i18n labels. Waiver bodies stay as statutory text in English.
- `events.py`: subscribe to `finance.payment.created` or `invoice.approved` to auto-request a waiver, and publish a deadline notification through `notifications`.
- `validators.py`: add a `lien.waiver_missing_for_payment` rule (WARNING/ERROR) in the validation pipeline.
- Optional `erp_chat/tools.py` tool: "which subs owe waivers?"
- Without third-party integrations, the Small part is about 1 to 2 weeks. A Levelset or Procore sync would add more.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Statutory form texts.** The official California forms are published by the CSLB (cslb.ca.gov) and are public law text, free to reproduce. Other states' statutes are also public.
- **Levelset (a Procore company).**
  - Free lien waiver and pay-app tools. Paid notice sending is around $59 per recipient. Lien filing requires a subscription.
  - Integrates with Procore, pushing signed docs into Procore Documents.
  - **No public developer API found**, so a direct connector is not currently feasible.
- **Procore REST API.** `GET /rest/v1.0/projects/{id}/lien_waivers?invoice_id=` and subtier waiver endpoints (conditional/unconditional), confirmed only through a third-party connector doc, not developers.procore.com. A Procore OAuth app is required.
- **MCP.** A community "procore-mcp-server" with a `list_lien_waivers` tool appears on glama.ai. I could not verify its license or maturity (the page was unreachable). No official lien-waiver MCP server exists.
- **Open source.** Only small, unvetted GitHub repos (e.g. "waiverflow" generators) turned up, with no mature licensed library. Build in-house.
- **Commercial alternatives** (no OSS): Built/lienwaivers.io, Siteline, CNS Lien free generators.
- **E-signature.** Not in the codebase. A simple typed-name and upload flow is enough to start. DocuSign/Dropbox Sign APIs are paid.

## Priority: 3/5 — High value for US subs and GCs and a cheap build on existing finance and contacts, but US-only, legally sensitive, with no Levelset API to integrate with.

## Sources
- https://www.cslb.ca.gov/consumers/legal_issues_for_consumers/Mechanics_Lien/Conditional_And_Unconditional_Waiver_Release_Form.aspx
- https://ezel.ai/surveys/mechanics-lien-waiver-rules
- https://www.levelset.com/preliminary-notice/
- https://www.levelset.com/tools/?role=all
- https://www.levelset.com/lien-waivers/lien-waiver-software/
- https://support.procore.com/integrations/levelset
- https://v2.support.procore.com/en-gb/faq-do-i-need-to-create-a-levelset-account-for-use-with-procore-pay/
- https://www.withone.ai/knowledge/procore/conn_mod_def%3A%3AGLdXw9ZFhQA%3A%3AZ0ciaf4eR52EpJCt4uzedg
- https://glama.ai/mcp/servers/TylerIlunga/procore-mcp-server/tools/list_lien_waivers
- https://www.siteline.com/compare/levelset
- https://getbuilt.com/lien-waiver-generator/
