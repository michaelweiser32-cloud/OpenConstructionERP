# 077. Browser Automation MCP (Playwright MCP, Puppeteer) for Supplier Portals and Permit Sites

## What it does
A browser automation layer lets an AI agent (or a scripted job) drive a real web browser. It can log into a supplier portal, look up current prices or stock for a list of materials, download a quote PDF, check a building permit's status on a municipal portal, or fill in repetitive web forms. Many of these sites have no public API. Browser automation is the "last-mile connector" for them.

Two ways to deliver it:
- **MCP route**: a browser MCP server, such as Microsoft's Playwright MCP, is attached to an AI agent like `erp_chat` or an external Claude, Cursor or other client. The agent navigates using accessibility-tree snapshots and proposes the extracted data. A human then confirms it before it enters the ERP. This follows the "AI-augmented, human-confirmed" rule.
- **Deterministic route**: recorded Playwright scripts ("recipes") run on a schedule for stable, repetitive checks, such as a nightly price refresh or a weekly permit-status poll.

## Already in the codebase (with file paths)
- `frontend/package.json`, `frontend/playwright.config.ts`: `@playwright/test` is used **only for E2E tests**. The backend has no runtime browser automation. The only "headless" dependency in `backend/pyproject.toml` is `opencv-python-headless`.
- `backend/app/modules/erp_chat/tools.py`: an internal tool registry (project, BOQ, schedule, validation and CWICR search handlers). It has no MCP client or web-browsing tool.
- `backend/app/modules/integrations/`: push-style messaging connectors (Slack, Teams, Telegram, WhatsApp, Discord, email). There is no pull or scrape connector.
- `backend/app/modules/procurement/`, `backend/app/modules/costs/`: these hold supplier and price data, but nothing ingests prices from supplier websites.
- `backend/app/core/plugin_manager.py`, `backend/app/core/marketplace.py`: module and plugin infrastructure that an optional connector could ship through.

**Gap:** everything is missing apart from the test-only Playwright dependency.

## Who it helps and how much
- **Small GCs and estimators** check distributor portals by hand for lumber, rebar, drywall and electrical prices. A semi-automated price check, saved as a proposed cost-item update with source URL and timestamp, saves hours per bid. The value is **medium**: it is fragile and site-specific.
- **Permit tracking**: many municipal portals have no API. A weekly status poll that creates a task or notification on change has modest but real value.
- **Limits:**
  - Supplier terms of service often forbid scraping.
  - Login credentials must be stored securely.
  - CAPTCHAs and MFA break unattended runs.
  - Selectors break when sites change.

  Each customer's portals are different, so this cannot ship as a turnkey core feature.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium**, as an optional plugin module `oe_browser_connector`, not core. This keeps the 2 GB VPS footprint, because Chromium adds roughly 300-500 MB.
- `manifest.py`: `depends=["oe_procurement", "oe_costs", "oe_notifications"]`, `auto_install=False`.
- `models.py`: `BrowserRecipe` (name, target site, Playwright script or MCP prompt, schedule) and `BrowserRun` (status, extracted JSON, screenshot or trace in storage, confidence). Credentials are referenced through an encrypted secret store and never kept in plain text.
- `service.py`: runs recipes with `playwright` (Python, Apache-2.0) in a Celery worker, or in-process in dev. Output goes to a **staging table**, never directly into cost items.
- `validators.py`: `ValidationRule`s for extracted prices, covering unit mismatch, more than X% deviation from the last price, missing currency, and stale timestamps.
- `erp_chat` integration: an optional MCP client in `erp_chat/tools.py` forwards `browser_*` tools from a configured Playwright MCP server, for ad-hoc "check this supplier page" questions.
- Frontend: a review queue for proposed price and permit updates, with accept/reject and a link to the screenshot evidence.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Playwright MCP** (Microsoft), https://github.com/microsoft/playwright-mcp. Apache-2.0, free.
  - Uses the accessibility tree, so no vision model is needed.
  - Supports `--headless`, `--isolated`, `--storage-state`, HTTP transport via `--port`, and a Docker image (headless Chromium).
  - This is the recommended choice.
- **Playwright for Python**, https://github.com/microsoft/playwright-python. Apache-2.0, free. Used for deterministic recipes.
- **Puppeteer MCP reference server**, https://github.com/modelcontextprotocol/servers-archived/tree/main/src/puppeteer. MIT, but **archived on 2025-05-29 and unmaintained**. Do not build on it.
- **browser-use**, https://github.com/browser-use/browser-use. An MIT Python agent library.
  - Its README mentions an MCP server and a CLI (details not verified here).
  - Its optional cloud browsers are listed at about $0.06 per browser-hour. It can also run a local Chromium with a local LLM.
- **Browserbase / Stagehand MCP**, https://docs.stagehand.dev/integrations/mcp-server. A hosted, paid browser service.
  - Third-party sources say the self-hosted MCP repo is archived and a hosted endpoint is offered instead.
  - **Pricing could not be verified** from the official page in this research.
  - Use it only as an optional cloud fallback for CAPTCHA- or stealth-heavy sites.

## Priority: 2/5 — useful glue for API-less supplier and permit portals, but fragile, ToS-sensitive and site-specific; ship later as an optional plugin with a human-review queue
Build structured price imports (CSV, EDI, supplier APIs) and the MCP client in `erp_chat` first.

## Sources
- https://github.com/microsoft/playwright-mcp
- https://github.com/microsoft/playwright-python
- https://playwright.dev/python/
- https://github.com/modelcontextprotocol/servers-archived/tree/main/src/puppeteer
- https://github.com/browser-use/browser-use
- https://docs.stagehand.dev/integrations/mcp-server
- https://www.browserbase.com/mcp
