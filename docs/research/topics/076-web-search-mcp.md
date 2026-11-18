# 076. Web search MCP servers (Brave, Tavily, Exa, Perplexity) for pricing and product research

## What it does
Gives the ERP's AI assistant live web access, so it can answer things like "current list price of 24 cm aerated concrete blocks", "find the datasheet for this fire-rated door", or "who supplies this product in my region". It does this through a web search API, called either as a Model Context Protocol (MCP) server or straight over REST. The results come back as ranked snippets with source URLs. The assistant uses them to *suggest* a unit rate, product spec or supplier, and an estimator then reviews it. The assistant never writes a price on its own, in line with the "AI-augmented, human-confirmed" principle.

## Already in the codebase (with file paths)
- `backend/app/modules/ai/ai_client.py` already lists **Perplexity as an LLM provider** (the `api.perplexity.ai/chat/completions` endpoint, around lines 263 and 516). It reads `perplexity_api_key` from `backend/app/config.py:160`. Sonar models answer with web grounding, but the citations are not stored or surfaced as structured evidence.
- `backend/app/modules/erp_chat/tools.py` defines internal tools only: `search_cwicr_database`, `search_boq_positions`, `search_documents`, `search_anything` and others. There is **no web search tool** and **no MCP client**. A grep for `mcp` or `modelcontextprotocol` in `backend/app` finds nothing.
- `httpx` is already a dependency (`backend/pyproject.toml`), and the project calls vendor REST APIs directly rather than through SDKs.

**Gap:** there is no provider-agnostic `web_search` tool for erp_chat, no citation or evidence storage, no per-tenant API key or budget settings, and no "suggested rate from the web" review flow.

## Who it helps and how much
- **Small estimators without a paid cost database** get quick market-price sanity checks, can find the cost of a material they have never priced, and can pull manufacturer datasheets. This saves real time on non-standard items. However, web prices are retail or list prices, so the value is medium-high as a *research aid* and low as a source of authoritative rates.
- **Procurement and RFQ users** can discover suppliers and alternative products for a substitution.
- **Submittals and RFI users** can find product data sheets and approvals quickly.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch)
**Small to Medium.**
1. Add `backend/app/modules/ai/web_search.py`, a small provider interface (`search(query, k) -> list[Result{title,url,snippet,date}]`) with httpx adapters for Brave, Tavily, Exa and the Perplexity Search API. The provider is selected per tenant in settings, with keys stored like the existing `*_api_key` fields. Calling REST directly avoids running Node-based MCP servers on a 2 GB VPS.
2. Register a `web_search` tool (and optionally `fetch_page`) in `erp_chat/tools.py`, gated by a permission in `ai/permissions.py` and a monthly query budget.
3. Optional: an MCP client mode that connects to the vendors' hosted Streamable-HTTP endpoints, for users who prefer that.
4. Add a `PriceEvidence` record (URL, snippet, retrieval date, confidence) that links to a BOQ position or cost item. The UI shows a "suggested" badge, and the estimator must accept it before the rate is written.
5. Add a validation rule in `boq_quality` that flags web-sourced rates that are unconfirmed or older than N days.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Brave Search MCP server**, <https://github.com/brave/brave-search-mcp-server>. MIT license. Tools include web, local, news, LLM-context and summarizer search; transport is STDIO or HTTP. The API reportedly gives a $5 monthly credit (about 1,000 queries), then costs about $5 per 1,000 requests. This comes from third-party reports; the official page could not be reached from this environment.
- **Tavily MCP**, <https://github.com/tavily-ai/tavily-mcp>. MIT license. Tools are search, extract, map and crawl, with a hosted endpoint at `mcp.tavily.com/mcp`. Pricing is 1,000 free credits a month with no card required, then $0.008 per credit pay-as-you-go (<https://docs.tavily.com/documentation/api-credits>).
- **Exa MCP server**, <https://github.com/exa-labs/exa-mcp-server>. MIT license. Hosted at `mcp.exa.ai/mcp`, with `web_search_exa` and `web_fetch_exa` tools. Search costs about $7 per 1,000 requests and contents about $1 per 1,000 pages (<https://exa.ai/docs/reference/pricing>).
- **Perplexity MCP server**, <https://github.com/perplexityai/modelcontextprotocol>. MIT license. Tools are search, ask, research and reason, with a hosted endpoint at `api.perplexity.ai/mcp`. The Search API costs $5 per 1,000 requests; Sonar and Agent calls add token fees (<https://docs.perplexity.ai/guides/pricing>).
- **Self-hosted option (not verified in this research):** SearXNG (AGPL-3.0) is a no-cost metasearch engine that can be self-hosted. I did not verify a specific MCP wrapper for it.

## Priority: 3/5 — cheap to add and useful for one-off price and datasheet lookups, but web prices are unreliable compared with curated cost databases and need human review.

## Sources
- https://github.com/brave/brave-search-mcp-server
- https://github.com/tavily-ai/tavily-mcp
- https://github.com/exa-labs/exa-mcp-server
- https://github.com/perplexityai/modelcontextprotocol
- https://docs.tavily.com/documentation/api-credits
- https://exa.ai/docs/reference/pricing
- https://docs.perplexity.ai/guides/pricing
- https://www.activepieces.com/blog/brave-search-api-pricing-plans-limits-cost-2026
