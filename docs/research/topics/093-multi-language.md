# 093. Multi-language workflow (i18n completeness, machine translation, translation platforms)

## What it does
This is the pipeline that keeps the UI, validation messages and backend strings complete in every supported language. It has four parts:
- **Extraction**: find every key used in code.
- **Completeness tracking**: report how much of each locale is translated, and fail CI when a key is missing.
- **Machine pre-translation**: DeepL, a self-hosted engine or an LLM fills gaps, and each result is marked "needs review".
- **Translation platform**: Weblate, Crowdin or Tolgee, where community translators and native-speaking staff fix strings without touching code.

A second, user-facing part is **content translation**. It translates BOQ position descriptions, specs or subcontractor RFQs into another language, with a human confirming each result (CLAUDE.md principle 7).

## Already in the codebase (with file paths)
- `frontend/src/app/i18n.ts`: i18next and react-i18next with 21 `SUPPORTED_LANGUAGES` (including RTL Arabic) and `fallbackLng: 'en'`. Modules add their own translations at runtime through `frontend/src/modules/_registry.ts`.
- `frontend/src/app/i18n-fallbacks.ts`: all locales sit in one bundled TS file of about 50,500 lines. EN takes about 3,300 lines. Most non-EN/DE locales take about 2,250–2,300 lines, roughly 69% coverage.
- `backend/app/core/i18n.py` and `i18n_router.py`: server-side `t()` with a `ContextVar` locale, loading `backend/locales/*.json`.
- `backend/locales/`: 20 files with no `bg.json`, so the backend is one locale behind the frontend. `en.json` has 372 keys and `fr.json` only 136.
- `audit/06-i18n.md`: an existing coverage audit that reached the same uneven-coverage conclusion.
- `scripts/add_users_i18n.py`: an ad-hoc script that pushes keys into locale files. It is the only "workflow" tooling.
- `backend/app/modules/i18n_foundation/`: covers countries, tax rules, calendars and ECB FX rates, not string translation.
- **Gaps**: no extraction or CI completeness gate, no TMS (Weblate, Crowdin or Tolgee) integration, no machine-translation adapter, and no content-translation tool in `ai` or `erp_chat`.

## Who it helps and how much
- **Small firms working in a non-English language**, for example PL, CZ or TR. They currently see English fallback in about 30% of the UI, which hurts adoption more directly than most features do. The impact is high for these markets.
- **Cross-border firms**: estimators who send RFQs to subcontractors abroad or receive specs in German or French. Content translation saves hours per tender.
- **The project itself**: a public Weblate or Crowdin project lets community translators close the gap at no cost. Without one, maintainers do all the translation work.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
The overall effort is **Medium**. It breaks into three phases.

1. **Small: tooling.**
   - Split `i18n-fallbacks.ts` into `frontend/src/locales/<lng>/<ns>.json`. These files can be lazy-loaded with an i18next backend, and every TMS can read them.
   - Add `i18next-cli extract --ci` and `status` to CI, plus a Python check that diffs `backend/locales/*.json` against `en.json`.
   - Add the missing `bg.json`.
2. **Small: Weblate integration.**
   - Connect the repo to Hosted Weblate on the Libre plan, or to self-hosted Weblate.
   - Translations arrive as PRs, so no runtime code is needed.
3. **Medium: new `translation` module.**
   - Add `backend/app/modules/translation/` with `manifest.py`, `service.py` and `router.py`.
   - The service uses a provider interface with adapters for DeepL, LibreTranslate and an LLM provider from the existing `ai` module.
   - Endpoints:
     - `POST /api/v1/translation/text`
     - `POST /api/v1/translation/boq/{id}`, which writes translated descriptions into position `metadata` marked `source=machine` and `confidence`, pending review
   - Integration points:
     - A validation rule `i18n.untranslated_positions` in `boq_quality`.
     - An `erp_chat/tools.py` tool called "translate this BOQ".
   - The provider is optional and is configured through settings, so the core stays lightweight.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **i18next-cli** (https://github.com/i18next/i18next-cli, MIT): `extract`, `status` and `sync` commands. The older alternative is i18next-parser (https://github.com/STRML/i18next-parser, MIT).
- **Weblate** (https://weblate.org/hosting/, GPL-3.0):
  - Self-hosting needs no licence.
  - Hosted Weblate's Libre plan is free on request for public projects, with the same limits as the 160k plan.
  - It syncs with Git and supports i18next JSON.
- **Crowdin** (https://crowdin.com):
  - Proprietary SaaS. A free Open Source licence is available on application; this was reported by a third party and not verified on an official Crowdin page.
  - Official hosted MCP server at `https://mcp.crowdin.com/v2/mcp`: https://support.crowdin.com/developer/crowdin-mcp-server/
- **Tolgee** (https://tolgee.io, Apache-2.0 core plus an enterprise licence):
  - Can be self-hosted, and offers in-context editing for React.
  - Official remote MCP server at `/mcp/developer` on Tolgee Cloud and on self-hosted instances: https://docs.tolgee.io/platform/integrations/mcp_server/about
  - A community MCP server also exists (`ytarfa/tolgee-mcp`, MIT).
- **DeepL API** (https://developers.deepl.com): the Free tier allows 500,000 characters per month. Pro pricing is usage-based; third-party sources quote figures that conflict, so verify on DeepL's site.
- **LibreTranslate** (https://github.com/LibreTranslate/LibreTranslate, AGPL-3.0): self-hosted and offline, built on Argos Translate. Its licence matches this project's AGPL. The public instance requires an API key.
- **LLM translation**: through the existing `ai` module. It handles construction terminology better given a glossary, and it costs per token.

## Priority: 4/5 — the 21-language promise is a core differentiator, but most locales are only about 69% translated, and cheap tooling (CI gate, Weblate, a DeepL or LibreTranslate pre-fill) closes the gap

## Sources
- https://weblate.org/hosting/
- https://weblate.org/try/
- https://docs.tolgee.io/platform/integrations/mcp_server/about
- https://tolgee.io/blog/localizing-a-react-app-with-the-tolgee-mcp-server
- https://support.crowdin.com/developer/crowdin-mcp-server/
- https://store.crowdin.com/crowdin-mcp-server
- https://support.deepl.com/hc/en-us/articles/360021200939-DeepL-API-Free
- https://github.com/LibreTranslate/LibreTranslate
- https://github.com/i18next/i18next-cli
- https://www.i18next.com/how-to/extracting-translations
- https://github.com/STRML/i18next-parser
