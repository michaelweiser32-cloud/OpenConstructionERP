# 091. Dashboards and PDF Reporting (report builder, branded PDFs, scheduled reports)

## What it does
Lets a small contractor or estimator turn project data (BOQ totals, cost vs budget, EVM, change orders, RFIs, safety, field reports) into dashboards they can read at a glance and PDFs they can send out: a cost summary for a client, a weekly progress report for the owner, a bid package cover. Three parts:
- **Report builder**: pick sections and widgets (KPI tiles, tables, charts) from a template and save it.
- **Branded PDF**: company logo, colours, letterhead, page numbers, header and footer, locale-aware number and currency formatting (i18n).
- **Scheduled delivery**: cron-based rendering that emails the PDF to a recipient list, plus a downloadable archive of every report produced.

## Already in the codebase (with file paths)
- `backend/app/modules/reporting/`: `KPISnapshot`, `ReportTemplate` (has `template_data`, `schedule_cron`, `recipients`, `is_scheduled`, `next_run_at`, `project_id_scope`) and `GeneratedReport` (`format`, `storage_key`, `data_snapshot`) models; routes for KPI history, templates, schedule, run-now, and generate/list reports; a stdlib cron parser in `cron.py`; system template seeding in `service.py`.
- `backend/app/main.py` (around line 1497): a 1-minute asyncio scheduler that picks up due templates and calls `generate_report`, with no Celery involved.
- `backend/app/modules/boq/pdf_export.py`: a full ReportLab BOQ PDF with cover page, header, footer and TOC. The brand name is hardcoded to the product name, not a tenant logo.
- `backend/app/core/email/` (SMTP, console and memory backends plus templates).
- Frontend: `frontend/src/features/dashboard/DashboardPage.tsx`, `features/reports/ReportsPage.tsx`, `features/reporting/ReportingPage.tsx`. `recharts`, `jspdf` and `jspdf-autotable` are already dependencies.

**Gap:** `ReportingService.generate_report` only writes a DB row. It renders no file, sets no `storage_key`, and sends nothing to `recipients`, so scheduled reports produce empty records. There is also no tenant branding profile (logo, colours, letterhead), no drag-and-drop widget layout, and portfolio-scope schedules get paused automatically.

## Who it helps and how much
High value for small firms. The owner of a 3 to 20 person firm sends the same weekly cost and progress summary to clients by hand, usually as Excel screenshots. A good-looking branded PDF that arrives on its own every Monday saves time and makes a small firm look professional next to larger competitors. Dashboards help the estimator or PM spot budget overruns early. A full BI-style builder matters less than "the templates look good and actually get sent".

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium**, mostly in `oe_reporting`:
1. **Renderer layer** (S to M): a `ReportRenderer` registry where modules contribute section renderers through the hook system (e.g. a `reporting.sections` filter: boq, full_evm, changeorders, safety each register a section). Render HTML with Jinja2, convert it to PDF with WeasyPrint (CSS paged media handles headers, footers and page counters), or reuse ReportLab, which is already a dependency. Store the file through `core/storage` and set `storage_key`.
2. **Branding profile** (S): a tenant-level model with logo, primary colour, address block and footer text, used as CSS variables in the PDF templates and in `boq/pdf_export.py`.
3. **Delivery** (S): after a scheduled render, send the PDF via `core/email` to `recipients` and publish a `reporting.report_generated` event so the `integrations` module (Slack, Teams, Telegram) can post a link.
4. **Builder UI** (M): a widget list stored in `template_data` (JSON), drawn with the existing recharts; add drag-and-drop layout later.
5. **Validation**: a rule that blocks or warns when a report is built on a BOQ with validation errors, plus a validation-score badge on the PDF cover.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **WeasyPrint**: HTML/CSS to PDF in pure Python with strong paged-media support. BSD-3-Clause. https://github.com/Kozea/WeasyPrint. It needs Pango system libraries and does not run JavaScript, so charts must be rendered server-side as SVG.
- **ReportLab** (already used): BSD open-source toolkit. https://www.reportlab.com/opensource/
- **Jinja2**: templating, BSD-3-Clause. https://jinja.palletsprojects.com/
- **Gotenberg**: Docker API for HTML/URL/Office to PDF using headless Chromium and LibreOffice. MIT. Optional sidecar for pixel-exact chart dashboards. https://github.com/gotenberg/gotenberg
- **Recharts** (already in frontend): MIT. https://recharts.org/
- **Metabase OSS**: AGPL-3.0, free to self-host. Static or guest embeds carry a "Powered by Metabase" badge; interactive embedding is paid (Pro or Enterprise). It has an official MCP server endpoint. Use it as an optional external BI connector, not as core. https://www.metabase.com/articles/is-metabase-embedding-free
- **Apache Superset**: Apache-2.0. It ships an MCP service in its repo (`superset/mcp_service`); community MCP servers also exist (e.g. bintocher/mcp-superset, MIT), but I did not verify how well maintained they are. https://github.com/apache/superset/blob/master/superset/mcp_service/README.md
- I found no construction-specific reporting MCP server. AI narrative summaries for reports can reuse the existing `ai` and `erp_chat` modules.

## Priority: 4/5 — the scaffolding (templates, cron, scheduler) already exists, but nothing renders or delivers yet; finishing that is a medium-sized job with high visible value for small firms.

## Sources
- https://github.com/Kozea/WeasyPrint
- https://pdf4.dev/blog/weasyprint-vs-prince
- https://github.com/gotenberg/gotenberg
- https://gotenberg.dev/
- https://www.reportlab.com/opensource/
- https://www.metabase.com/articles/is-metabase-embedding-free
- https://www.metabase.com/pricing.md
- https://mcpservers.org/servers/metabase-mcp-server
- https://github.com/apache/superset/blob/master/superset/mcp_service/README.md
- https://github.com/bintocher/mcp-superset
