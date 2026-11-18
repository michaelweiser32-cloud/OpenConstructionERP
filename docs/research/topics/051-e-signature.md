# 051. E-signature (DocuSign, Dropbox Sign, Adobe Sign, Documenso / OpenSign / DocuSeal)

## What it does
Sends a generated document (quote/estimate PDF, subcontract, change order, payment application, daily report, inspection sign-off, transmittal receipt) to one or more external signers, places signature/date/initial fields, tracks status (sent, viewed, signed, declined), and returns a completed PDF plus an audit trail (certificate of completion). Status changes come back by webhook. A provider abstraction lets each installation pick a hosted SaaS (DocuSign, Dropbox Sign, Adobe Acrobat Sign) or a self-hosted open-source server (DocuSeal, Documenso, OpenSign).

## Already in the codebase (with file paths)
- `backend/app/modules/fieldreports/models.py`: `signature_by` / `signature_data` fields on field reports (an in-app captured signature, not a legally tracked envelope). Used in `fieldreports/service.py` and `router.py`.
- `backend/app/modules/cde/models.py`: a `signature` string on CDE state-transition records (approval stamp on a gate, no external signer flow).
- `backend/app/core/file_signature.py`: file *magic-byte* detection. It has nothing to do with e-signatures.
- `backend/app/modules/integrations/`: outbound webhooks with HMAC `X-Webhook-Signature` and email/chat connectors. This can be reused for delivery and inbound-webhook patterns.
- PDF generation already exists (for example `backend/app/modules/boq/pdf_export.py`).
- **Gap:** there is no e-signature module, envelope model, provider connector, signer workflow, or completed-document storage hook, and no PAdES/cryptographic PDF signing.

## Who it helps and how much
Small contractors and estimators win work by getting quotes and change orders signed quickly. Signing an estimate or change order from inside the ERP removes the print-sign-scan step and shortens the time to "approved". It also gives an auditable record for disputes over change orders and payment applications. The value is **High** for change orders, subcontracts and client proposals, and Medium for internal sign-offs (daily reports, inspections), where the existing in-app signature is often enough. Many small firms already pay for DocuSign or Dropbox Sign, so connecting to their existing account matters more than building a new provider.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Build a new module, `backend/app/modules/esign/`, with these parts:
- `models.py`: `SignatureEnvelope` (provider, external_id, status, target_type/target_id such as `changeorder` or `boq_export`, document_id, completed_document_id) and `EnvelopeRecipient`.
- `providers/`: a `SignatureProvider` protocol (`create_envelope`, `get_status`, `download_completed`, `verify_webhook`). Start with DocuSeal (self-hosted, simple REST API) and DocuSign. Add Dropbox Sign, Documenso and OpenSign behind the same interface.
- `router.py`: `POST /envelopes`, `GET /envelopes/{id}`, and an inbound `POST /webhooks/{provider}` that verifies HMAC.
- `events.py`: publish `esign.envelope.completed` and `esign.envelope.declined` on the event bus. `changeorders` and `tendering` subscribe and move the record to "approved". The signed PDF is stored through `documents`/`cde` storage.
- `validators.py`: block sending when the document has no signers, a signer email is invalid, or the PDF is missing. Show a warning when an approved change order is unsigned.
- Frontend: a "Send for signature" action on change order, BOQ export and subcontract pages, plus a status badge. Every string goes through i18n.
- Optional: local PAdES sealing of exported PDFs with pyHanko, for tamper evidence without any provider.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **DocuSeal**: <https://github.com/docusealco/docuseal>. Licensed AGPL-3.0, self-hostable. It has a REST API, webhooks and a Python client (`docuseal` on PyPI). Hosted API use costs about $0.20 per completed document on Pro, according to third-party guides, so check the official pricing.
- **Documenso**: <https://github.com/documenso/documenso>. The Community Edition is AGPL-3.0. The docs list some API, embedding and webhook features as Enterprise items, so check the features table first. Hosted pricing: <https://documenso.com/pricing>.
- **OpenSign**: <https://github.com/OpenSignLabs/OpenSign>. Licensed AGPL-3.0, with a separately licensed sub-directory, so check the LICENSE file. It has a key-authenticated REST API, documented at <https://docs.opensignlabs.com>.
- **DocuSign eSignature REST API and official MCP server**: <https://developers.docusign.com/platform/mcp-server>. The MCP server is generally available, with endpoints `mcp.docusign.com/mcp` (production) and `mcp-d.docusign.com/mcp` (demo). It can send envelopes, track status and run workflows. It is a paid commercial service, and a free developer sandbox is available.
- **Dropbox Sign API**: <https://sign.dropbox.com/api>. Paid tiers start at $75/month billed annually, according to the vendor page. `test_mode` is free. I could not verify an official MCP server.
- **Adobe Acrobat Sign REST API**: <https://developer.adobe.com/acrobat-sign/>. Commercial and requires an enterprise or API plan. I did not verify an official MCP server.
- **pyHanko**: <https://github.com/MatthiasValvekens/pyHanko>. MIT-licensed. Does PAdES B-B through B-LTA signing, RFC 3161 timestamps and PKCS#11, for local cryptographic sealing.
- Licensing note: the AGPL servers run as separate services called over HTTP, which fits OpenConstructionERP's AGPL license. Do not vendor their code into the ERP.

## Priority: 4/5 — Signed change orders and proposals are a daily money-relevant workflow for small firms, and the work is a medium-sized connector with mature APIs and a self-hosted open-source option.

## Sources
- https://developers.docusign.com/platform/mcp-server
- https://www.docusign.com/blog/developers/docusign-mcp-server-general-availability
- https://www.docuseal.com/signing-api
- https://www.docuseal.com/resources/use-webhooks
- https://pypi.org/project/docuseal/
- https://docs.documenso.com/users/licenses/community-edition
- https://docs.documenso.com/docs/policies/enterprise-edition
- https://documenso.com/pricing
- https://github.com/OpenSignLabs/OpenSign
- https://sign.dropbox.com/api
- https://help.dropbox.com/plans/how-much-does-the-dropbox-sign-api-cost
- https://developer.adobe.com/acrobat-sign/
- https://pypi.org/project/pyHanko/
