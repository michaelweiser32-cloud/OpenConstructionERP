# 070. Semantic cost-item matching (embeddings + vector search)

## What it does
Given a BOQ line such as "Stahlbetonwand C30/37, 24 cm" or "200mm blockwork wall", the system finds the best-fitting items in a cost database (CWICR, regional packs, the user's own rate library) by meaning rather than exact keywords. It works across languages and unit conventions. It returns ranked candidates with a confidence score, a suggested rate and classification codes. Following the "AI-augmented, human-confirmed" principle, a person accepts each match; nothing is applied automatically.

## Already in the codebase (with file paths)
A lot of this is already built. The main gaps are match quality and the workflow around it.
- `backend/app/core/vector.py`: embedded LanceDB by default, Qdrant optional (`VECTOR_BACKEND=qdrant`). Embeddings come from FastEmbed or sentence-transformers. The default model is `intfloat/multilingual-e5-small` (384 dim), with `all-MiniLM-L6-v2` as the fallback (`backend/app/config.py`). Results can be filtered by region.
- `backend/app/core/vector_index.py`, `vector_routes.py`: a generic multi-collection index with per-module adapters (`modules/*/vector_adapter.py`).
- `backend/app/modules/costs/router.py`: `semantic=true` autocomplete, `/vector/status/`, `/vector/regions/`, `/vector/index/`.
- `backend/app/modules/boq/service.py` / `router.py`: `classify_position`, `suggest_rate` (weighted by similarity, returns the matches it used) and `search_cost_items` (AI Cost Finder with unit, region and min_score filters).
- Frontend: `frontend/src/features/boq/BOQModals.tsx`, `frontend/src/features/boq/api.ts`, `frontend/src/features/costs/CostsPage.tsx`.

**Gaps found:**
1. `encode_texts()` does not add the `query: ` / `passage: ` prefixes that the E5 model card requires. This likely costs retrieval quality right now; it is a one-line fix.
2. Search is vector-only. There is no hybrid search (BM25/full-text plus vector), so exact codes, dimensions and grades such as "C30/37" or "DN100" can rank poorly.
3. There is no cross-encoder reranking step.
4. There is no bulk "match the whole BOQ" job with a review queue (accept, reject or pick another candidate).
5. Accepted matches are not stored, so the system cannot learn a company's own phrasing or boost previously chosen items.
6. Unit compatibility is an exact filter only. Conversions such as m2 vs m3 with a thickness, or "t" vs "kg", are not handled.

## Who it helps and how much
High value for small estimators. Pricing an imported BOQ or tender LV line by line against a 55K-item database is the most time-consuming manual step. A good matcher with a review queue can cut the first pricing pass from hours to minutes, and it helps when the cost database and the tender are in different languages. The risk is wrong but confident matches, so confidence bands, unit checks and validation rules matter as much as raw recall.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch)
**Medium** overall. The steps below can each ship on their own.
- **S:** Add E5 prefixes in `core/vector.py` (passage when indexing, query when searching) and re-index. Record the prefix scheme in the index metadata.
- **S/M:** Hybrid search. LanceDB has native full-text search with an RRF reranker; Qdrant supports sparse vectors (BM25 via FastEmbed). Put this behind the existing `vector_search` API.
- **M:** Optional reranking of the top 50 with FastEmbed `TextCrossEncoder` (`BAAI/bge-reranker-base`, MIT), configurable and off on 2GB VPS installs.
- **M:** A `boq` background job, "auto-match BOQ", that writes `MatchSuggestion` rows (position_id, cost_item_id, score, rank, status). Results show as a review grid in the BOQ editor, and the job publishes a `boq.match.completed` event through the event bus.
- **S:** Validation rules in `boq_quality`: matched unit mismatch, low-confidence match accepted, and rate outlier compared with candidates.
- **S/M:** A feedback store of accepted pairs, used as a per-tenant boost or few-shot examples for the existing `ai` module.

## Building blocks (free/open-source libs, APIs, MCP servers)
- LanceDB (Apache-2.0): embedded vector DB with built-in full-text and hybrid search and an RRF reranker. https://lancedb.com/docs/search/hybrid-search
- FastEmbed (Apache-2.0): ONNX embeddings, sparse BM25/SPLADE vectors and cross-encoder rerankers. Note that `jina-reranker-v2-base-multilingual` is CC-BY-NC-4.0, so avoid it in commercial builds. https://qdrant.tech/documentation/fastembed/fastembed-rerankers/
- multilingual-e5-small (MIT): already the default; requires query/passage prefixes. https://huggingface.co/intfloat/multilingual-e5-base
- Qdrant (Apache-2.0): server option with hybrid dense plus sparse search.
- pgvector (PostgreSQL License): could fit the single-database principle as a third backend. Not checked in this pass.
- MCP: I found no dedicated, verified MCP server for construction cost matching. The better route is to expose the existing search as an `erp_chat` tool, or as a project MCP tool later.

## Priority: 4/5. The base is built; fixing the E5 prefixes, adding hybrid search and adding a bulk review queue would give the largest time saving for small estimators at modest effort.

## Sources
- https://lancedb.com/docs/search/hybrid-search
- https://docs.lancedb.com/reranking/rrf
- https://qdrant.tech/documentation/fastembed/fastembed-rerankers/
- https://huggingface.co/intfloat/multilingual-e5-base
- https://mixpeek.com/guides/do-e5-and-bge-embeddings-need-query-and-passage-prefixes

Note: in this research session huggingface.co, lancedb.github.io and qdrant.github.io could not be fetched directly. The claims above rely on web search summaries of those official pages.
