# 009. Classification mapping: Uniformat II, OmniClass, MasterFormat, NRM, DIN 276 crosswalks

## What it does
A crosswalk service lets one BOQ position, cost item or CAD element carry codes in several classification systems at once (e.g. DIN 276 KG 330 / NRM 1 2.5 / Uniformat II B2010 / MasterFormat 04 20 00 / Uniclass EF_25_10). The estimator classifies once. The ERP then produces the other views: cost-plan roll-ups by element (Uniformat/NRM 1/DIN 276), trade packages for tendering (MasterFormat/NRM 2/GAEB), and BIM hand-over codes (OmniClass/Uniclass). Mappings are many-to-many and lossy, so each link needs a confidence value and a human review step, in line with the "AI-augmented, human-confirmed" principle.

## Already in the codebase (with file paths)
- `backend/app/modules/cad/classification_mapper.py`: deterministic Revit/IFC category to DIN 276, NRM 1 and MasterFormat dicts (about 30 categories). It has no Uniformat, OmniClass or Uniclass mappings.
- `frontend/src/modules/_shared/classificationMap.ts`: a 66-line hard-coded cross-reference table (DIN 276, NRM, MasterFormat, French lots, ACMM).
- `frontend/src/features/boq/ClassificationPicker.tsx` and `EstimateClassification.tsx`: picker UI and per-standard roll-up.
- `backend/app/core/validation/rules/__init__.py`: rules for DIN 276, NRM and MasterFormat (required code, valid code, completeness, hierarchy). There are no Uniformat or OmniClass rules.
- `backend/app/modules/us_pack/config.py` and `backend/app/modules/uk_pack/config.py` declare the standards (MasterFormat 2018, UniFormat II, NRM 1/2/3). `backend/app/schemas.py` has an `omniclass` field. `CreateProjectPage.tsx` offers OmniClass as an option.
- **Data-quality gap found:** the two tables contradict each other and also contradict DIN 276:2018. In `classificationMap.ts`, DIN 321/322 are labelled shallow/deep foundations, but they are really 321 Baugrundverbesserung, 322 Flachgründungen und Bodenplatten, 323 Tiefgründungen. KG 370-372 are labelled finishes, but in the 2018 edition 370 is Infrastrukturanlagen. NRM 2.1 is labelled "External walls", but in NRM 1 2.1 is Frame and 2.5 is External walls (the backend has this right). The backend maps all doors and windows to 340, but external openings are 334. There is no single source of truth on the backend, and the tables have no versions and no confidence values.

## Who it helps and how much
- Small firms working across borders or for international clients (DACH/UK/US): high value. Today they re-key codes by hand.
- US estimators: Uniformat II elemental early estimates that turn into MasterFormat trade bids is the standard workflow. This is medium-high value.
- UK QS firms: NRM 1 to NRM 2 and Uniclass mapping is needed for BIM Level 2/ISO 19650 deliverables.
- Correct mappings also improve cost matching and AI classification, because codes act as anchors for vector search.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Steps:
1. Create a new `backend/app/modules/classifications/` module with a manifest. Its models would be `ClassificationSystem` (code, edition, license note), `ClassificationNode` (code, parent, title i18n) and `ClassificationMapping` (src, dst, relation `exact|broader|narrower|related`, confidence, source).
2. Seed it from `data/classifications/*.csv`, one file per edition. Ship full trees only where the license allows (see below). For licensed systems, ship structure only and let the user import their own licensed files.
3. Add the endpoint `GET /api/v1/classifications/crosswalk?from=din276&code=330&to=uniformat`. Add a hook `classification.resolve` so that `cad`, `boq`, `costs` and the regional packs consume one service. Then replace `classification_mapper.py` and the frontend table with API calls.
4. Add validation rules `uniformat_valid_element` and `crosswalk_consistency` (codes on one position must not contradict each other).
5. Add an optional bSDD lookup adapter and expose `classify`/`crosswalk` as `erp_chat/tools.py` tools.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **NIST IR 6389 (Uniformat II)**: https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nistir6389.pdf. This is a US government publication and the best free source for the element tree. The ASTM E1557 standard itself is paid.
- **buildingSMART Data Dictionary (bSDD) REST API**: https://github.com/buildingSMART/bSDD (repo is MIT; the data has per-dictionary terms). Swagger: https://app.swaggerhub.com/apis/buildingSMART/Dictionaries/v1. It includes Uniclass, OmniClass and DIN 276-based dictionaries and has public read endpoints.
- **bSDD MCP server**: https://github.com/JardiMargalefAgusti/bSDD-mcp (MIT, 9 read tools, no API key). It is a small community project, so treat it as experimental.
- **Uniclass 2015 (NBS)**: https://uniclass.thenbs.com/. Free download. Confirm the redistribution terms before bundling.
- **OmniClass / MasterFormat / UniFormat (CSI)**: https://www.csiresources.org/omniclass. Licensed through CSI. CSI's paid Crosswalk tool maps MasterFormat, UniFormat and OmniClass; I did not find a public API price. Do not bundle full tables. Ship division-level codes plus a user import.
- **NRM (RICS) and DIN 276 (DIN Media)**: copyrighted and paid. Ship codes plus short titles only. Full texts are user-supplied.
- I found no dedicated MasterFormat, NRM or DIN 276 MCP server.

## Priority: 4/5 — the plumbing exists, but the crosswalk data is wrong and spread across files; a single, correct, versioned crosswalk service is a medium-effort fix that every estimating, CAD and tendering workflow relies on.

## Sources
- https://nvlpubs.nist.gov/nistpubs/Legacy/IR/nistir6389.pdf
- https://www.csiresources.org/omniclass
- https://www.forconstructionpros.com/construction-technology/news/21207427/astm-international-csis-uniformat-astms-uniformat-ii-linked-within-crosswalk
- https://uniclass.thenbs.com/
- https://github.com/buildingSMART/bSDD
- https://app.swaggerhub.com/apis/buildingSMART/Dictionaries/v1
- https://github.com/JardiMargalefAgusti/bSDD-mcp
- https://www.weka.de/architekten-ingenieure/kostengruppe-300/
- https://www.thenbs.com/knowledge/what-is-the-buildingsmart-data-dictionary
