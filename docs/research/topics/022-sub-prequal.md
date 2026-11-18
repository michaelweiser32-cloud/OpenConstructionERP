# 022. Subcontractor Prequalification (questionnaires, financials, safety EMR, licenses)

## What it does
Prequalification lets a general contractor (GC) check whether a subcontractor can take on a job before inviting it to bid or awarding work. The usual workflow:
- The subcontractor fills in a questionnaire: company profile, trades, past projects, references, bonding capacity, financial summary, safety program, experience modification rate (EMR) for the last 3 years, OSHA 300A logs, licenses and insurance certificates (COIs).
- The GC scores the answers and approves the subcontractor with a limit, for example a maximum contract value or certain trades.
- The system tracks expiry dates (license, COI, EMR year, approval itself) and sends reminders.
- Approval status gates the RFQ bidder list and contract award.

Commercial tools such as PreQual, Billy, ISNetworld, Avetta and Highwire either charge per vendor or require you to contact sales for a price. For a small firm the typical setup is still spreadsheets plus emailed PDFs. Industry-standard forms such as ConsensusDocs 721 define the usual set of questions. In Germany the equivalent is a public registry: the PQ-VOB directory run by PQ-Verein.

## Already in the codebase (with file paths)
- `backend/app/modules/contacts/models.py` has free-form JSON lists `certifications` and `insurance`, a `prequalification_status` string and `qualified_until`. That date is stored as a string, not a date type.
- `backend/app/modules/contacts/repository.py` counts `with_expiring_prequalification` for the stats endpoint. `backend/app/modules/contacts/schemas.py` exposes these fields.
- `frontend/src/features/contacts/ContactsPage.tsx` shows a status badge (`PREQUAL_CONFIG`, pending/approved/...).
- `backend/app/modules/rfq_bidding/models.py` links bids to contacts, but nothing stops an unqualified subcontractor from being invited.

**Gap:** the codebase has none of the following:
- a questionnaire or template engine
- structured EMR, financial or license records
- a document-backed COI with limits, endorsements and expiry
- a scoring model
- a subcontractor self-service portal or link
- expiry reminders through `notifications`
- a check that blocks unqualified bidders in `rfq_bidding` or `procurement`

## Who it helps and how much
- **Small GCs and estimators:** High value. It replaces chasing COIs and EMR letters by email, lowers the risk of an uninsured subcontractor on site, and speeds up building bid lists.
- **Specialty subcontractors using the ERP for their own sub-tier:** Medium value.
- **Public-sector bidders:** Medium value. Prequalification is often mandatory there (PQ-VOB in Germany; surety and bonding in the US).

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Effort: Medium.** A new module `oe_prequal` (`backend/app/modules/prequal/`) that depends on `oe_contacts`, `oe_documents` and `oe_notifications`.

- **Data models:**
  - `PrequalTemplate`: a JSON question schema, versioned, with presets seeded from regional packs (US: ConsensusDocs-721-like; UK: PAS 91-like; DACH: PQ-VOB checklist).
  - `PrequalSubmission`: answers, attached documents and a score.
  - `QualificationRecord`: type (EMR, license, COI, bond, financial), value, issuer, `valid_from`/`valid_to`, a document link and a verified flag.
- **Scoring rules:** use the existing `core/validation` engine with a rule set `prequal`. Example rules: EMR above 1.0 gives a warning; an expired COI is an error; general-liability limits below the project minimum are an error.
- **Events and hooks:**
  - The module publishes `prequal.approved` and `prequal.expiring`.
  - It registers a filter hook on the `rfq_bidding` bidder invite so an expired or unqualified subcontractor triggers a warning or a block. The GC makes the final decision.
  - A daily expiry scan sends notifications.
- **Subcontractor portal:** a tokenized, unauthenticated form link where the subcontractor fills in the questionnaire.
- **Later, optional:** AI extraction of COI and EMR-letter fields with confidence scores. The user must confirm the values before they are saved.
- **Migration:** move the free-form `contacts.insurance` and `certifications` lists into `QualificationRecord`.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **SurveyJS Form Library** (https://github.com/surveyjs/survey-library): MIT-licensed JSON-schema forms for React. The visual Survey Creator needs a paid commercial license. A plain JSON-Schema renderer is a lighter alternative.
- **ConsensusDocs 721** (https://www.consensusdocs.org/contract/721-statement-of-qualifications/): reference for the question set. The document itself is paid and copyrighted, so only the generic categories can be reused, not its text.
- **SAM.gov Exclusions API** (https://open.gsa.gov/api/exclusions-api): checks US federal debarment. Free, needs a public API key and has daily rate limits.
- **DOL / OSHA enforcement data** (https://enforcedata.dol.gov/views/agency_tools.php, https://dataportal.dol.gov/registration): OSHA inspection and violation history. Free, needs an API key. The old enforcedata site is being retired, so the endpoint should be checked before building on it.
- **PQ-VOB directory** (https://www.pq-verein.de): public lookup of German prequalified companies. I found no documented public API, so the module would store the PQ number and a link, not an automated check.
- **MCP servers:** I found no official MCP server for prequalification, COI or EMR. Only third-party Apify scrapers exist, and they are unverified and should not be relied on.
- **Benchmarks:** commercial products as a reference for features and pricing, not integrations: PreQual (https://www.vertikalrms.com/article/subcontractor-prequalification-software-guide-2026/) and Billy (https://billyforinsurance.com/vendor-prequalification-general-contractors).

## Priority: 4/5 — the data fields already exist, so a medium-sized module would close a real risk and time gap for small GCs and fits the validation-first design
The basic fields exist but there is no workflow behind them. Expired COIs and unqualified bidders are a real liability for small GCs. The work fits the validation engine and hooks that already exist, and it needs no paid dependency.

## Sources
- https://www.consensusdocs.org/contract/721-statement-of-qualifications/
- https://open.gsa.gov/api/exclusions-api
- https://enforcedata.dol.gov/views/agency_tools.php
- https://enforcedata.dol.gov/views/faq.php
- https://www.osha.gov/pls/imis/establishment.html
- https://www.pq-verein.de/fileadmin/dokumente/PQ_Hinweisblatt_kommunale_AG.pdf
- https://www.bauprofessor.de/praequalifikation-vob/
- https://github.com/surveyjs/survey-library
- https://surveyjs.io
- https://www.vertikalrms.com/article/subcontractor-prequalification-software-guide-2026/
- https://billyforinsurance.com/vendor-prequalification-general-contractors
- https://safetyculture.com/app/contractor-prequalification-software/
