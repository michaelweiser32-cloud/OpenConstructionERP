# 021. Tender / Bid Package Management and Bid Leveling

## What it does
A general contractor or estimator breaks the estimate into trade packages (for example concrete, drywall or MEP), invites subcontractors, collects their priced bids, and then *levels* them. Leveling puts every bid on the same scope: it records what each bidder included and left out, adds "plug" values for items a bidder did not price, normalises alternates and allowances, and then shows the real low bidder. The winning unit rates then go back into the budget or BOQ. Without leveling, a low number often just means missing scope.

## Already in the codebase (with file paths)
- `backend/app/modules/tendering/`: `TenderPackage` (linked to a BOQ) and `TenderBid`, which stores `line_items` as JSON. It has CRUD, a position-by-bid comparison matrix with deviation from the BOQ budget (`service.compare_bids`), an apply-winner step that copies the winning unit rates into the BOQ (`/packages/{id}/apply-winner/`), a PDF export, and a cross-package bid analysis with IQR outliers and spread (`/bid-analysis/`).
- `backend/app/modules/rfq_bidding/`: RFQs with `issued_to_contacts`, bids and a `BidEvaluation` schema. This partly overlaps with tendering.
- `backend/app/modules/boq/router.py`: GAEB XML 3.3 export (X83) and import (X83/X84). Import fills BOQ positions, not tender bids.
- `frontend/src/features/tendering/TenderingPage.tsx` and `BidComparisonChart.tsx`.

**Gap:**
- No scope checklist of inclusions and exclusions per bid.
- No plug values or "normalised total" for unpriced lines.
- No alternates or allowances.
- No tracking of invitations or bid intent (will bid / declined).
- No link for subs to submit a bid without logging in.
- No import of a returned Excel bid form or a GAEB X84 file *into a TenderBid*.
- No soft award or leveling notes.
- No scorecard that weights price, schedule and qualification.
- `tendering` and `rfq_bidding` duplicate each other.

## Who it helps and how much
**High** value for small GCs and estimators who send 5–20 packages per job. Today they level bids in spreadsheets. Commercial tools lock leveling into paid tiers: BuildingConnected includes Bid Leveling only with BC Pro, and SmartBid is listed from about $450/month. An open, BOQ-linked leveling sheet that feeds the estimate directly is a strong selling point. In DACH markets the GAEB X83 → X84 round-trip (Preisspiegel) is expected by default.

## Implementation effort
**Medium**, in `tendering` (core), `boq` (GAEB/Excel parsers), `contacts` (bidder directory) and `notifications`/`integrations` (invites).
- Extend `TenderBid.line_items` to a typed schema with `included`, `excluded`, `plug_rate`, `alternate` and `note`. Add a `normalized_total` computed in `service.compare_bids`.
- Add a `TenderInvite` model holding contact_id, status and a token. A tokenised public endpoint lets a sub upload an Excel bid form or a GAEB X84 file, which is parsed into a bid. The parsers already used by `boq` can be reused.
- Emit events through `app.core.events`, such as `tendering.bid.submitted` and `tendering.package.awarded`, so that notifications and erp_chat tools can respond.
- Add validation rules (`bid_quality`): unpriced lines, quantity mismatch against the package, outliers beyond the IQR, and missing mandatory inclusions.
- Merge `rfq_bidding` into `tendering`, or clearly separate the two (procurement RFQs vs. subcontract tenders).
- Keep it human-confirmed: any AI scope-gap detection only *suggests* plugs, each with a confidence score.

## Building blocks
- **pygaeb**: parses, validates and writes GAEB DA XML 2.0–3.3, including X84 bids and X86 price matching. MIT, v1.21.0. https://pypi.org/project/pygaeb/ (repo https://github.com/frameiq/pygaeb)
- **gaeb-parser**: a small MIT parser that turns GAEB files into pandas. https://pypi.org/project/gaeb-parser/
- **openpyxl** (MIT): generates and re-imports Excel bid forms, which is the most common format for subs.
- **BuildingConnected API (Autodesk Platform Services)**: REST read/write for bid packages, invites, bids and opportunities. Access requires BC Pro / Bid Board Pro and a sales contact, and it cannot publish bid packages. Suited to an optional connector module. https://aps.autodesk.com/en/docs/buildingconnected/v2/developers_guide
- **Procore Bid Management REST API**: bid packages and bids endpoints (`/rest/v1.x/projects/{id}/bid_packages/{id}/bids`). Requires a Procore subscription. https://developers.procore.com
- **MCP**: a community "procore-mcp-server" is listed with a read-only `bid_level_across_a_bid_form` tool. I could not verify its license or how well it is maintained. I found no official vendor MCP server for bid leveling. A better route is to expose our own leveling tools through `erp_chat/tools.py`.

## Priority: 4/5 — core estimating workflow with a solid base already in place; scope leveling, sub invites and X84/Excel bid import close the main gap cheaply.

## Sources
- https://support.buildingconnected.com/hc/en-us/articles/360018938534-What-actions-taken-on-the-Bid-Leveling-tab-are-visible-and-not-visible-to-subcontractors
- https://buildxact.com/us/blog/what-is-the-process-of-bid-leveling/
- https://www.selecthub.com/p/construction-bidding-software/smartbid/
- https://aps.autodesk.com/en/docs/buildingconnected/v2/developers_guide
- https://aps.autodesk.com/blog/buildingconnected-write-api-released
- https://developers.procore.com
- https://pypi.org/project/pygaeb/
- https://pypi.org/project/gaeb-parser/
- https://glama.ai/mcp/servers/TylerIlunga/procore-mcp-server/tools/bid_level_across_a_bid_form
