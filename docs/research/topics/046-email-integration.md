# 046. Email integration: inbound email to RFI/correspondence (Gmail API, Microsoft Graph, IMAP/SMTP)

## What it does
Small contractors run their projects from the inbox. Subcontractors send questions, architects send revised drawings and clients send approvals, and the official record ends up scattered across personal mailboxes. Inbound email integration would connect a shared project mailbox, or a per-project alias such as `project-123@inbound...`. Each incoming message would be parsed for sender, subject, body, attachments and thread headers. The system would match it to a project and contact, then propose a Correspondence entry, an RFI draft or a document upload. Replies sent from the ERP keep the thread together through `In-Reply-To` and `References` headers. In keeping with "AI-augmented, human-confirmed", the classifier only suggests "this looks like an RFI for project X", with a confidence score. Nothing is filed until a user confirms it.

## Already in the codebase (with file paths)
- Outbound only. `backend/app/core/email/` has a pluggable `EmailBackend` (`smtp.py`, `console.py`, `memory.py`, `noop.py`) and `service.py` with templates (password reset, task assigned, meeting invitation and others). `backend/app/modules/integrations/email_service.py` is a compatibility shim over it.
- `backend/app/modules/integrations/schemas.py` lists `email` as an integration type with an SMTP config only.
- `backend/app/modules/correspondence/models.py` already models `direction` (incoming/outgoing), `from_contact_id`, `to_contact_ids`, `date_received`, `linked_document_ids` and `linked_rfi_id`. This makes it the natural target for inbound mail.
- `backend/app/modules/rfi/` and `contacts/` exist.
- **Gap:** I found no IMAP, Gmail API or Microsoft Graph code, no `.eml`/`.msg` parsing, no mailbox OAuth and no thread matching.

## Who it helps and how much
- PMs and estimators in firms of 2 to 30 people who use plain Gmail or Microsoft 365. They get one audit trail per project instead of personal inboxes, plus fewer lost RFIs and change requests, which matters in disputes.
- The value is high because email is the main channel in small firms, and the data model already exists. Without capture, the RFI and correspondence modules depend on manual entry and tend to go unused.

## Implementation effort
**Medium (M).** Phase 1 (IMAP plus `.eml` upload) is Small. Gmail and Graph push are Medium because of OAuth app registration and verification.
- New module `backend/app/modules/email_inbox/` (manifest depends on `oe_correspondence`, `oe_rfi`, `oe_contacts`, `oe_documents`):
  - `models.py`: `MailAccount` (provider = imap/gmail/graph, encrypted credentials or OAuth refresh token, cursor = IMAP UID, Gmail `historyId` or Graph `deltaLink`) and `InboundMessage` (raw message stored via `core/storage`, parsed fields, status pending/filed/ignored, suggested target, confidence).
  - `providers/`: the inbound counterpart to `core/email/base.py`, i.e. an `InboxProvider` ABC with `fetch_since(cursor)` and per-provider implementations.
  - Sync: a Celery task or an in-process poller for IMAP. Gmail uses `users.watch` with a Pub/Sub push to a webhook route followed by `users.history.list`. Graph uses a `/subscriptions` webhook on messages plus a delta query for catch-up.
  - Matching: project code or `[RFI-012]` in the subject, a plus-address or alias, thread headers, and the sender domain mapped to a contact's company. An optional LLM classifier lives in `modules/ai`.
  - Events: publish `email.received` and let hooks in correspondence/rfi create drafts. Validation rules flag cases like unknown sender, missing project match or oversized attachment.
  - Frontend: a "Project inbox" triage list with Accept → Correspondence / RFI / Document.
- Outbound: add a Gmail/Graph send backend under `core/email/` so replies go out from the user's real mailbox.

## Building blocks
- Python stdlib `imaplib`, `email`, `smtplib` (PSF license, no dependency). It covers IMAP/SMTP and MIME parsing.
- imap-tools, https://github.com/ikvk/imap_tools. Apache-2.0, high-level IMAP API with IDLE support.
- aioimaplib, https://github.com/iroco-co/aioimaplib. Async IMAP with IDLE, **GPL-3.0**. AGPL-compatible but limits the commercial dual licence, so prefer imap-tools or the stdlib.
- Gmail API push (`users.watch` + Cloud Pub/Sub, watch renewal every 7 days). Free API quota; Pub/Sub has a free tier. Restricted Gmail scopes need Google OAuth verification. https://developers.google.com/gmail/api/guides/push
- Microsoft Graph change notifications plus delta query on messages. Included with Microsoft 365; needs an Entra app registration. https://learn.microsoft.com/graph/change-notifications-overview
- MCP: the Google Gmail MCP server is reported to be in developer preview (read, search, label, draft, no send), according to third-party coverage I could not confirm on a Google page. Softeria ms-365-mcp-server (MIT, Graph-based, community) has mail tools. Both suit ad-hoc AI assistant use through `erp_chat`, not reliable backend ingestion.

## Priority: 4/5 — email is the main channel in small firms, the target data model exists, and IMAP gives a cheap dependency-free first step; OAuth providers add moderate effort.

## Sources
- https://developers.google.com/gmail/api/guides/push
- https://developers.google.com/gmail/api/v1/reference/users/watch
- https://learn.microsoft.com/graph/change-notifications-overview
- https://pnp.github.io/blog/post/microsoft-graph-webhook-delta-query/
- https://github.com/ikvk/imap_tools
- https://pypi.org/project/imap-tools/
- https://github.com/iroco-co/aioimaplib
- https://github.com/softeria/ms-365-mcp-server
- https://www.dragapp.com/blog/gmail-mcp-server/
