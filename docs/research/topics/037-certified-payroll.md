# 037. Certified payroll (US WH-347, prevailing wage / Davis-Bacon, LCPtracker)

## What it does
Contractors on US federally funded public works (Davis-Bacon and Related Acts) and on many state prevailing-wage jobs must pay at least the wage and fringe rates in the applicable **wage determination (WD)**. They must also file a weekly **certified payroll** with a signed Statement of Compliance. The federal form is **WH-347**. USDOL revised it in 2025, adding a worker entry number, a journeyworker/registered-apprentice column and the WD number, and it later published an online fillable version. Many states and agencies require electronic submission instead: California DIR eCPR XML (V1/V2 XSD), Washington L&I, Maryland, NYSDOL and others, often through a compliance portal such as LCPtracker. For a small contractor this involves three jobs:
1. bid with the correct prevailing rates,
2. record hours by classification for each worker and job,
3. export a compliant weekly report and check that the rates paid meet the WD rates.

## Already in the codebase (with file paths)
- **No certified-payroll, WH-347, Davis-Bacon or LCPtracker code.** Searches of backend and frontend found nothing.
- `backend/app/modules/fieldreports/models.py` has `oe_fieldreports_workforce` entries that log headcount, `hours_worked` and `overtime_hours` by trade/company per daily report. They are aggregates, not per-worker timecards, and the hours are stored as strings.
- `backend/app/modules/us_pack/` (config/manifest/router) covers AIA G702, MasterFormat, units and sales tax, but has no labor-compliance config.
- `backend/app/modules/finance/models.py` has invoices, payments and budgets, but no payroll.
- `docs/research/topics/004-public-cost-data.md` already notes there is no Davis-Bacon lookup and that SAM.gov has no verified API.

## Who it helps and how much
- **US small subcontractors and GCs bidding public work: High.** Certified payroll is mandatory, it is a frequent source of findings and withheld payments, and it is weekly paperwork.
- **Estimators:** Medium value. WD rates loaded as labor rates make public bids more accurate.
- **Non-US users:** none. This belongs in an optional US module.
- Most small firms already run payroll in QuickBooks, ADP, Paychex or a construction payroll product. Many of those, plus LCPtracker itself, already produce WH-347 output. The realistic win is narrower: clean per-worker hours by WD classification, a WH-347-layout PDF, and CSV/XML exports for upload, not a replacement payroll engine.

## Implementation effort
**Medium** for a useful MVP; **Large** if it calculates gross-to-net payroll, which is out of scope and not recommended.
- New optional module `oe_certified_payroll` (`depends=["oe_projects","oe_us_pack"]`, `auto_install=False`) with these models:
  - `WageDetermination`: WD number, county, modification number, classifications with base and fringe rates, entered manually or parsed from the SAM.gov text file.
  - `Worker`
  - `WeeklyPayroll`, with lines for daily hours ST/OT by classification, rate paid, fringe paid or cash-in-lieu, and deductions entered from the external payroll.
- Validation rules in the existing framework:
  - `prevailing_wage.rate_below_wd`
  - `apprentice_ratio`
  - `missing_classification`
  - `overtime_over_40h`
- Exports:
  - a WH-347-style PDF with the Statement of Compliance, via the reporting module
  - CA DIR eCPR XML validated against the published XSD
  - a generic CSV in the LCPtracker upload-template layout
- Import hours from `fieldreports` workforce logs, or by CSV from the payroll system. Emit events such as `certified_payroll.submitted`.
- Costs integration: offer WD rates as labor rates for public-work estimates (human-confirmed).

## Building blocks
- **SAM.gov wage determinations**: free, public, distributed as text/PDF. **No official API found**, so ingest by manual upload and parse. https://sam.gov/wage-determinations
- **CA DIR eCPR XML guidelines / XSD V2**: free public schema; validate with `lxml` (BSD). https://www.dir.ca.gov/Public-Works/cpr/eCPR-XML-Guidelines-V2.pdf
- **LCPtracker / LCPcertified**: commercial. Its knowledge base says **no Certified Payroll API is available**. Integration is by spreadsheet/XML upload (spreadsheet template capped at 200 records per upload) or direct payroll interfaces with Paychex, QuickBooks and others. A free single-contractor tier was announced in 2018; I did not verify current pricing.
- **WH-347 form**: public-domain USDOL form. The form could not be fetched in this session because dol.gov was not reachable, so its details come from vendor summaries.
- **PDF generation**: whatever the reporting module already uses, or ReportLab (BSD).
- **MCP**: **no certified-payroll or Davis-Bacon WD MCP server found.** The adjacent servers I found are listed below; none produces WH-347 or WD rates:
  - `bls-oews-mcp`: market wages, MIT license
  - `gsa-calc-mcp`: GSA contract labor rates
  - DOL WHD enforcement-data MCP servers

## Priority: 3/5 — mandatory and painful for US public-works small contractors, but US-only and already served by payroll products; ship as an optional us_pack add-on with WD rates, hours capture, validation and exports.

## Sources
- https://sam.gov/wage-determinations
- https://www.dol.gov/agencies/whd/government-contracts/prevailing-wage-resource-book/db-wage-determinations
- https://www.dol.gov/newsroom/releases/whd/whd20251216-0
- https://lcptracker.com/blog-post/faq-how-to-complete-the-revised-wh-347-form/
- https://kb.lcptracker.com/support/solutions/articles/154000236744-contractor-wh-347-form-key-updates-faq-updated-2-24-25-
- https://kb.lcptracker.com/support/solutions/articles/154000261388-september-2026-release
- https://kb.lcptracker.com/support/solutions/articles/154000182291-contractor-dir-export-instructions
- https://lcptracker.com/solutions/lcpcertified/
- https://www.codot.gov/business/civilrights/compliance/assets/cdot-lcptracker-contractor-user-guide.pdf
- https://www.dir.ca.gov/Public-Works/cpr/eCPR-XML-Guidelines-V2.pdf
- https://dir.ca.gov/Public-Works/Certified-Payroll-Reporting.html
- https://pypi.org/project/bls-oews-mcp
- https://prnewswire.com/news-releases/lcptracker-introduces-free-subscription-tier-for-single-contractor-certified-payroll-solution-300748819.html
