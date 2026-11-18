# 018. Marketplace module ideas and monetization

## What it does
A module marketplace lets a small contractor or estimator install add-ons such as regional cost databases, exchange formats (GAEB, NRM, MasterFormat), connectors and AI packs without a developer. Monetization turns that catalog into a source of funding through paid modules, subscriptions for data packs, or a revenue share with third-party authors. For a small business the marketplace is mainly a discovery and one-click-install surface. For the project it is the commercial layer on top of the AGPL core.

## Already in the codebase (with file paths)
- `backend/app/core/marketplace.py` is a static catalog of 67 `MarketplaceModule` entries: cost databases, vector indices, languages, converters, analytics, integrations and demo projects. It already has a `price` field (`"Free" | "Pro" | "$9.99/mo"`), but every entry is set to `"Free"`.
- `backend/app/core/plugin_manager.py` installs a module from a zip, URL or registry (`DEFAULT_REGISTRY_URL = https://registry.openestimate.io/api/v1`) and checks for updates. It does not verify hashes or signatures, and it has no license or entitlement check.
- `backend/app/core/module_loader.py` and `module_state.py` handle discovery, dependencies and enable/disable.
- The frontend has module packages in `frontend/src/modules/*`, about 20 regional `*-exchange` packs, and a module guide at `frontend/src/modules/MODULE_DEVELOPMENT_GUIDE.md`. `MODULES.md` points to the "Settings → Modules & Marketplace" UI.

**Gap:** there is no package signing, no license keys or entitlements, no payment or checkout, no vendor onboarding and no reviews or ratings. The registry URL is hard-coded, and I could not verify that it is live.

## Who it helps and how much
- **Small estimating firms (Medium–High):** they can install a regional pack, a cost DB and an exchange format in minutes. A signed, curated catalog builds trust, which matters because a module runs as Python inside the ERP.
- **Project and maintainers (High):** recurring revenue from data packs (regional rates, which need yearly updates), "Pro" connectors (accounting, Procore-style PM sync) and hosted AI credits. Odoo's model shows this works: Odoo keeps 30% of app sales and 25% of in-app purchases.
- **Third-party module authors (Medium):** a revenue share gives local estimators a reason to package their country rules. Procore's partner program instead charges no fees and gets its value from listings.

Promising paid categories:
- Annually updated regional cost data
- National tender formats (GAEB X83/X86 extended, NRM2)
- Accounting connectors
- AI takeoff credits
- Premium validation rule sets (client-specific QA)

The core and basic modules stay free.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium overall**, split into three increments:
1. **S – Trust:** add a `sha256` field and a signature bundle to registry entries. `plugin_manager._install_from_zipfile` verifies them with `sigstore-python` before extracting. Unsigned zips are refused unless the admin turns on a dev flag.
2. **M – Entitlements:** add an optional `license` block to `ModuleManifest` (`sku`, `features`). A new `core/licensing.py` validates an offline-verifiable signed license file or a Keygen license key. The module loader skips or degrades a paid module that has no valid entitlement. Free modules are untouched.
3. **M/L – Commerce:** registry-side checkout through Stripe Connect, with author payouts and a platform fee. This stays outside the self-hosted app: the app only stores the issued license. The frontend marketplace page reads the `price` field it already has.

**Legal note:** paid modules that load into an AGPL-3.0 core need care. Either the core team dual-licenses its own modules, or third-party authors accept AGPL source availability and charge for data, updates and support. This needs a legal review before launch.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **sigstore-python:** sign and verify artifacts, Apache-2.0. https://github.com/sigstore/sigstore-python
- **cosign sign-blob:** the alternative CLI signer, Apache-2.0. https://docs.sigstore.dev/cosign/signing/signing_with_blobs/
- **Keygen CE:** self-hostable licensing API (keys, entitlements, machine activation), under the Fair Core License, free to self-host. https://github.com/keygen-sh/keygen-api
- **Stripe Connect:** marketplace payouts. Pricing is about $2 per active account per month plus 0.25% + 25¢ per payout in the US when the platform handles onboarding. stripe.com could not be reached from this session, so check the live page. https://stripe.com/connect/pricing
- **Reference models:**
  - Odoo Apps (30% / 25% commission): https://www.odoo.com/apps/upload
  - Grafana Marketplace and Enterprise plugins (paid plugins on top of an AGPL core): https://grafana.com/blog/grafana-marketplace
  - Procore App Marketplace (no partner fees): https://developers.procore.com/partner
- **MCP:** I did not find a verified MCP server for plugin marketplaces or licensing. Installed modules could instead expose their own tools through `erp_chat/tools.py`.

## Priority: 3/5 — signing and entitlements are cheap and unlock sustainable funding, but the marketplace only pays off once enough paid-worthy modules exist
Add signing first, because it is a security need. Licensing and checkout come after the core workflows are solid.

## Sources
- https://www.odoo.com/apps/upload
- https://developers.procore.com/partner
- https://procore.github.io/documentation/partner-overview
- https://grafana.com/blog/grafana-marketplace
- https://grafana.com/blog/grafana-enterprise-data-source-plugins-a-brief-guide-to-what-they-are-and-how-to-get-started
- https://docs.sigstore.dev/cosign/signing/signing_with_blobs/
- https://blog.sigstore.dev/announcing-the-1-0-release-of-sigstore-python-4f5d718b468d
- https://github.com/keygen-sh/keygen-api
- https://keygen.sh/blog/keygen-is-now-fair-source/
- https://stripe.com/en-us/connect/pricing
