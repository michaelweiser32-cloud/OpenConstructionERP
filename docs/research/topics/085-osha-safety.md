# 085. OSHA Safety Compliance (Toolbox Talks, Incident Reports, OSHA 300/300A Logs, ITA Submission)

## What it does
US employers covered by 29 CFR Part 1904 must record work-related injuries and illnesses on OSHA Form 301 (incident report), keep a yearly Form 300 log, and post the Form 300A summary from Feb 1 to Apr 30. Under 29 CFR 1904.41, covered establishments must also file electronically through OSHA's Injury Tracking Application (ITA) by March 2 each year. Construction (NAICS 23) is a designated high-hazard industry, so establishments with 20+ employees must file 300A data, and larger ones must also file 300/301 case data. You can file three ways: a web form, a CSV upload, or a REST API that uses a per-account API token. OSHA also runs a preview (sandbox) environment for testing. Toolbox talks are short, documented safety briefings held before work starts. They provide evidence of training and are often required by GC/owner contracts.

## Already in the codebase (with file paths)
- `backend/app/modules/safety/models.py`: `SafetyIncident` (incident_number, incident_date, incident_type, severity, injured_person_details JSON, treatment_type, days_lost, root_cause, corrective_actions, `reported_to_regulator` flag, status) and `SafetyObservation` (risk matrix: severity x likelihood).
- `backend/app/modules/safety/router.py`: CRUD, `/stats/`, `/trends/`, and Excel export for incidents and observations.
- `backend/app/modules/safety/service.py`: counts recordables (medical/hospital/fatality treatments) and computes TRIR.
- `frontend/src/features/safety/SafetyPage.tsx`: the UI.
- `backend/app/modules/meetings/router.py`: classifies a meeting as "safety" when it detects keywords such as "toolbox talk", "osha" or "jsa". There is no dedicated toolbox-talk entity yet (topic, attendee sign-off, language).
- `backend/app/modules/us_pack/`: US regional pack. It has no OSHA recordkeeping logic.

**Gap:** the code has no OSHA case classification (days away / restricted / job transfer / other recordable, injury vs. illness type, privacy case). It also lacks establishment entities (address, NAICS, annual average employees, total hours worked) and 300/300A/301 form generation (PDF or equivalent). There is no ITA CSV export, ITA API client, 300A certification workflow, or toolbox-talk library with attendance records.

## Who it helps and how much
US small GCs and specialty subs with 20 to 250 workers are exactly the high-hazard establishments that must file. Today most of them keep the 300 log in a spreadsheet and re-type it into ITA every March. Generating the forms automatically from incident records saves hours each year and lowers the risk of citations for late or missing filings. Toolbox-talk records with crew sign-off help with EMR/insurance reviews and GC prequalification. The value is high for US users and none outside the US, though the same entities can feed RIDDOR (UK) or BG reporting (DACH) packs.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Modules touched: `safety` and `us_pack`. The `meetings` module could be reused for toolbox talks.
- `safety`: add an `osha` JSONB block (or columns) to `SafetyIncident`: case classification, injury/illness category, days away/restricted, privacy-case flag, and date of death. Add an `Establishment` model (NAICS, size, hours worked per year) plus a `ToolboxTalk` model (topic, language, attendees, signatures, linked project).
- `us_pack`: add an `osha_recordkeeping` service that builds 300/300A/301 data, renders PDFs through the existing reporting module, and exports CSVs matching OSHA's ITA data dictionaries. An optional ITA API client would take the token from the user's own settings or secrets store and should target the preview environment first.
- Validation rules (`us_osha.*`): recordable case missing a classification, 300A totals not matching the 300 log, missing hours worked, privacy-case names not masked. These fit the existing validation framework.
- Events: `safety.incident.created` triggers a reminder about the 8h/24h severe-injury reporting rule (29 CFR 1904.39). A seasonal notification fires for the Feb 1 posting date and the Mar 2 filing deadline.
- AI (human-confirmed): suggest a recordability determination and toolbox-talk topics based on the current schedule activities.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **OSHA ITA API + CSV specs**: free government service that needs an ITA account and API token. Docs: https://www.osha.gov/sites/default/files/ita_case_data_api_specifications.pdf and https://www.osha.gov/injuryreporting/osha_ita-estab-and-summary-csv-documentation_revised.pdf
- **ITA preview sandbox**: https://preview.osha.gov/injuryreporting/ita (free).
- **OSHA forms 300/300A/301**: public domain, and "equivalent forms" are allowed. Software-generated equivalents are acceptable if they contain the same information.
- **CPWR toolbox talks (EN/ES)**: free from a nonprofit. Reuse terms need checking before content is bundled, so link to it instead of copying it.
- **NC DOL construction toolbox reviews (EN/ES)**: free state publication.
- **MCP servers**: community "osha-recordkeeping-mcp" (recordability determination under Part 1904, listed on glama.ai). I did not verify its license or maintenance. `regulations-mcp` on PyPI covers eCFR / Federal Register lookups. There is **no official OSHA/DOL MCP server**.
- **Libraries**: reportlab/WeasyPrint (already a typical PDF path) and stdlib `csv` for ITA exports. No new heavy dependencies are needed.
- **Commercial comparators**: SafetyCulture, LogStead and Salus all generate 300 logs or ITA CSVs. I found no open-source 300-log generator.

## Priority: 4/5 — required by law each year for US construction firms with 20+ employees, and the safety module already holds most of the incident data, so adding OSHA fields and an ITA export is a contained Medium job with high payoff for US users.

## Sources
- https://osha.gov/300A
- https://osha.gov/injuryreporting
- https://www.osha.gov/injuryreporting/faqs
- https://www.osha.gov/sites/default/files/ita_user_guide.pdf
- https://www.osha.gov/sites/default/files/ita_case_data_api_specifications.pdf
- https://www.osha.gov/injuryreporting/osha_ita-estab-and-summary-csv-documentation_revised.pdf
- https://www.osha.gov/sites/default/files/ita_case_data_csv_specifications.pdf
- https://osha.gov/sites/default/files/view-api-token.pdf
- https://www.osha.gov/recordkeeping/finalrule/
- https://www.labor.nc.gov/documents/files/construction-tool-box-reviews
- https://www.ishn.com/articles/103488-asse-and-cpwr-release-workplace-safety-resources-for-at-risk-construction-workers
- https://glama.ai/mcp/servers/qa5j0bgz2z
- https://pypi.org/project/regulations-mcp
- https://www.mondaq.com/unitedstates/health-safety/1753384/fast-approaching-deadline-osha-injury-and-illness-data-due-march-2-2026

Note: osha.gov could not be fetched directly from the research environment. The details above come from search-result summaries of OSHA's own pages. Check the exact API endpoints and the NAICS Appendix A/B thresholds against eCFR 29 CFR 1904.41 before implementing.
