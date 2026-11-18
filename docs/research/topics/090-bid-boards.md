# 090. Bid boards and lead sources (SAM.gov, Dodge, ConstructConnect, BidNet, TED EU tenders)

## What it does
A "bid board" module pulls public and commercial tender notices into the ERP as **opportunities**. It filters them by trade code (NAICS/PSC in the US, CPV in the EU), region and value. The user can mark an opportunity go/no-go and turn it into a project, a tender package or an RFQ with one click. That covers the step before estimating: finding work worth pricing. Today small firms do this by hand, with email alerts and spreadsheets.

## Already in the codebase (with file paths)
- No lead or opportunity ingestion exists. A grep for SAM.gov, TED, Dodge, ConstructConnect, BidNet, NAICS and CPV finds nothing under `backend/app` or `frontend/src`.
- `backend/app/modules/tendering/` (`TenderPackage`, `TenderBid`) covers the *outbound* side: sending bid packages to subcontractors and comparing their bids.
- `backend/app/modules/rfq_bidding/` (`RFQ`, `RFQBid`) handles supplier quotes.
- `backend/app/modules/integrations/` (slack, teams, telegram, email...) can send alerts for new matching notices.
- `backend/app/modules/contacts/` can hold issuing agencies and buyers.
- `backend/app/modules/erp_chat/tools.py` could expose a "search opportunities" tool.
- Gap: everything upstream of a project, meaning the source connectors, the opportunity model, saved searches and go/no-go tracking.

## Who it helps and how much
- **Small general contractors and specialty subs who bid public work** (US federal/state, EU above-threshold tenders): high value. SAM.gov and TED are free, authoritative feeds that replace manual daily checks.
- **Firms bidding mostly private work**: medium value. The best private leads come from Dodge and ConstructConnect, which are paid, closed products.
- **Pure estimating consultancies**: low value.

## Implementation effort
**Medium** for a new module `bid_board` plus the free connectors.
- `manifest.py` declares `oe_bid_board`, depending on `oe_projects`, `oe_tendering` and `oe_contacts`.
- `models.py` has `Opportunity` (source, external_id, title, buyer, codes, location, value, due_date, url, status), `SavedSearch` and `SourceConfig`.
- There is one connector class per source behind a common `LeadSource` interface: `search(query) -> list[Opportunity]`. Each source is pluggable, so a paid connector can ship as a separate marketplace module.
- A scheduled job (the existing background-task path or the workflow engine) runs saved searches, de-duplicates on `(source, external_id)`, and publishes an `opportunity.matched` event. The integrations module listens for that event and sends notifications.
- A validation rule set `bid_board` flags notices with a missing due date, a past deadline or no trade-code match.
- Service actions convert an opportunity into a `Project` or a `TenderPackage`.
- Frontend: a `features/bid-board` list and kanban view (New / Reviewing / Bidding / Submitted / Won / Lost).
- The paid connectors (ConstructConnect, Dodge) would each be **Small** once the customer holds an API contract. BidNet would be **Large** or not feasible, because it has no public API.

## Building blocks
- **SAM.gov Get Opportunities Public API v2**: official GSA REST API with a free API key from a SAM.gov account. Limits are low for non-federal accounts (third-party sources report about 10 calls per day; check your own account). Some packages say keys expire after 90 days. https://open.gsa.gov/api/get-opportunities-public-api/
- **TED API v3** (EU Publications Office): `POST https://api.ted.europa.eu/v3/notices/search` with expert-query syntax. Anonymous access works for published notices, under a fair-usage policy. https://docs.ted.europa.eu/api/latest/index.html
- **ConstructConnect Project Intelligence / Construction Data API**: commercial. Key-based access through a developer portal, tied to a paid subscription. Returns JSON, XML or CSV. Pricing is only available through sales. https://www.constructconnect.com/products/project-intelligence/construction-data-api
- **Dodge Construction Network**: its marketing mentions "API and automation" and CRM sync. I found **no public developer docs**, so access is unverified and needs an enterprise agreement.
- **BidNet Direct**: **no public API found**. A third-party directory says none exists. Scraping would likely breach its terms of service, so don't build on it.
- **Existing MCP servers** (community-built, not official; review them before use): `sam-gov-mcp` on PyPI (opportunities, entities, exclusions) https://pypi.org/project/sam-gov-mcp/ and a Government Contracts MCP (SAM.gov plus USAspending) listed on mcpservers.org. I found no official TED, Dodge or ConstructConnect MCP server. A native Python connector (`httpx`, already in the stack) is simpler than adding an MCP dependency.

## Priority: 3/5 — the free official feeds (SAM.gov, TED) make a cheap, distinctive lead-to-estimate funnel for public-work bidders, but the private sources are paywalled or closed
## Sources
- https://open.gsa.gov/api/get-opportunities-public-api/
- https://docs.ted.europa.eu/api/latest/index.html
- https://docs.ted.europa.eu/api/endpoints/ted-europa-eu.html
- https://www.constructconnect.com/products/project-intelligence/construction-data-api
- https://www.construction.com/subcontractors/
- https://www.getapp.com/operations-management-software/a/bidnet-direct
- https://pypi.org/project/sam-gov-mcp/
- https://mcpservers.org/de/servers/github-com-martc03-gov-mcp-servers-tree-main-servers-gov-contracts-mcp
