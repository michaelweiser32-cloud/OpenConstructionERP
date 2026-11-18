# 012. CPM scheduling with MS Project (MSPDI XML) and Primavera P6 XER import/export

## What it does
CPM scheduling computes early and late dates, float and the critical path from activities, logic links (FS/SS/FF/SF plus lag) and calendars. Round-trip interchange with Microsoft Project (MSPDI XML, the documented `mspdi_pj12.xsd` schema) and Oracle Primavera P6 (XER, a tab-delimited table dump) lets a small contractor take an owner's or GC's programme, link it to BOQ positions and cost, update progress, and send it back in the format the client asked for.

## Already in the codebase (with file paths)
- `backend/app/core/cpm.py` (317 lines): an async CPM engine with forward and backward pass, all four link types plus lag, and work-day and holiday calendars.
- `backend/app/modules/schedule/router.py`:
  - CPM endpoints: `/schedules/{id}/calculate-cpm/`, `/schedule/cpm/calculate/` and `/critical-path/`.
  - Baselines, progress updates, risk analysis, `/generate-from-boq/`.
  - `POST /schedule/import/xer/` (`_parse_xer_tables`): reads the TASK, TASKPRED and CALENDAR tables. Calendars are stored only as raw metadata.
  - `POST /schedule/import/msp-xml/`: MSPDI import. Calendars are not mapped.
  - `GET /schedule/export/csv/`: the only export.
- `backend/app/modules/schedule/models.py`: Activity has `total_float`, `free_float`, a constraint type and a free-form `resources` JSON. `ScheduleRelationship` stores the link type and `lag_days`.
- `backend/app/modules/schedule/service.py`: a duplicate legacy `calculate_critical_path` (FS/SS only).
- Frontend `frontend/src/features/schedule/SchedulePage.tsx`: exports TSV only; `api.ts` never calls the import endpoints.

**Gaps:**
- No XER or MSPDI export.
- No upload UI for either format.
- Per-activity calendars are not mapped into CPM.
- No WBS (PROJWBS) or resource (RSRC/TASKRSRC) mapping.
- No validation rule set for schedule quality, which the project's "validation always" rule requires.
- Two CPM implementations exist.

## Who it helps and how much
- Subcontractors and small GCs bidding public or commercial work are often required to submit schedules in P6 XER or MS Project format. Native export lets them bid without buying a licence.
- Estimators get BOQ-driven durations and a cost-loaded schedule that feeds `full_evm`.
- Value: **high** for firms working on owner-mandated schedules. **Medium** for small residential builders, who mostly need a simple Gantt chart.

## Implementation effort
**Medium**, touching the `schedule` module, `core/cpm.py` and the `validation` module.
1. Add pure-Python writers in `schedule/interchange/`: `xer_writer.py` (ERMHDR plus the PROJECT, CALENDAR, PROJWBS, TASK and TASKPRED tables) and `mspdi_writer.py` (stdlib `xml.etree`). Move the existing parsers there from `router.py`.
2. Map calendars properly, both XER `clndr_data` and MSPDI `<Calendars>`, into the `cpm.py` calendar dict. Support per-activity calendars.
3. Retire the CPM in `service.py` in favour of `core/cpm.py`.
4. Add a `schedule_quality` rule set in `core/validation/rules/`, inspired by the DCMA 14-point checks: missing logic, negative float, high float, long durations, hard constraints, open ends. Run it after import.
5. Frontend: an import/export dropdown, an import preview with the validation report, and i18n keys.
6. Optional plugin module `oe_schedule_mpxj`: a JVM-backed sidecar using MPXJ for MPP, PMXML and the other formats it covers. Optional, to keep core lightweight.
7. Optional: CPM tools in `erp_chat/tools.py`.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **MPXJ** (https://github.com/joniles/mpxj): LGPL-2.1 per its GitHub README. Reads MPP, MSPDI, XER, PMXML and many others, and writes MSPDI, XER, PMXML and MPX. It is Java with a PyPI wrapper and needs a JVM. PyPI lists a different licence; check first.
- **PyP6Xer** (https://pypi.org/project/PyP6XER/): an XER parser, LGPL-2.1-or-later.
- **xerparser** (jjCode01): an XER reader, GPL-3.0-only. Fine for AGPL, but blocks the commercial edition.
- **cpp-xer-parser** (https://github.com/danafitkowski/cpp-xer-parser): MIT per PyPI, reads and writes XER. Not reviewed in depth.
- **MCP servers (community, not affiliated with Oracle or Microsoft):**
  - `paulieb89/pyp6xer-mcp`: MIT, 29 tools covering critical path, float, quality, EVM and XER write-back.
  - `osama-ata/p6xer-mcp-server`: MIT, 13 read and analysis tools.
  - `jeffersonbim/lean-planning-mcp`: reads MS Project, P6 and Synchro; licence not checked.
  - No official Oracle or Microsoft MCP server was found.
- **Specs:**
  - Microsoft MSPDI schema reference (Learn) and the `mspdi_pj12.xsd` schema at schemas.microsoft.com.
  - Oracle P6 Importing and Exporting Guide v24. Note that Oracle's guides disagree on whether baselines can travel in XER.

## Priority: 4/5 — the CPM engine and both importers already exist, so adding XER/MSPDI export, calendar fidelity and a schedule validation rule set closes a gap that blocks bids at moderate cost.

## Sources
- https://github.com/joniles/mpxj
- https://pypi.org/project/mpxj/
- https://pypi.org/project/PyP6XER/
- https://github.com/danafitkowski/cpp-xer-parser
- https://github.com/paulieb89/pyp6xer-mcp
- https://github.com/osama-ata/p6xer-mcp-server
- https://github.com/jeffersonbim/lean-planning-mcp
- https://learn.microsoft.com/en-us/office-project/xml-data-interchange/project-xml-data-interchange-schema-reference?view=project-client-2016
- https://docs.oracle.com/cd/F88968_01/English/admin/p6_pro_importing_exporting/p6_pro_importing_exporting.pdf
- https://docs.oracle.com/cd/F37128_01/English/admin/p6_pro_importing_exporting/export_projects_to_an_xer_file.htm
