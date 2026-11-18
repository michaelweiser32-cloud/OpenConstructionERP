# 065. Chat-with-project: RAG over project docs, BOQ, schedule and correspondence

## What it does
A per-project assistant that answers natural-language questions such as "what concrete grade does the spec require for the foundation slab?", "which RFIs are still open on the roof?", or "how much of the budget goes to KG 300 and which activities are late?". Every answer carries clickable citations back to the source record: a document page, a BOQ position, a schedule activity, an RFI, a meeting minute or a transmittal. Retrieval pulls from both unstructured text (PDF specs, contracts, minutes) and structured ERP data (BOQ, schedule, cost model). In line with the project's AI-augmented, human-confirmed principle, the assistant only reads and cites; any write it proposes needs explicit confirmation.

## Already in the codebase (with file paths)
Much of the infrastructure is already built. The remaining gap is content depth and citations.
- **Vector layer:** `backend/app/core/vector.py` uses LanceDB by default (embedded) and Qdrant as an option, with a multilingual embedding model. `backend/app/core/vector_index.py` defines the `EmbeddingAdapter` protocol and the collections `oe_boq_positions`, `oe_documents`, `oe_tasks`, `oe_risks`, `oe_bim_elements`, `oe_requirements`, `oe_validation` and `oe_chat`. Routes live in `backend/app/core/vector_routes.py`.
- **Adapters:** `vector_adapter.py` exists in the `boq`, `documents`, `tasks`, `risk`, `bim_hub`, `requirements`, `validation` and `erp_chat` modules.
- **Chat with tool calling:** `backend/app/modules/erp_chat/tools.py` provides `get_project_summary`, `get_boq_items`, `get_schedule`, `get_risk_register`, `search_documents`, `search_boq_positions`, `search_anything`, `create_boq_item` and others, with project-access checks. Unified search is in `backend/app/modules/search/`.
- **PDF tooling:** `pdfplumber` and `pymupdf` are already dependencies (`backend/pyproject.toml`). `documents/service.py` uses pdfplumber for sheet splitting.

**Gaps:**
1. `documents/vector_adapter.py` embeds only the name, description, category and tags. File contents are never extracted, chunked or indexed, so the assistant cannot answer questions about what a spec or contract says.
2. Correspondence is not indexed at all. That covers `rfi`, `submittals`, `transmittals`, `meetings`, `changeorders` and inbound email (`integrations/email_service.py` only sends).
3. Schedule activities are reachable only through the structured tool, not semantic search.
4. There is no chunk-level citation (page or offset) in answers, and no hybrid search (BM25 plus vector) or reranking.
5. There is no MCP server, so external assistants cannot query the project.

## Who it helps and how much
- **Small GC or estimator (1-20 staff):** High value. These firms have no document controller, so finding the right clause, RFI answer or change order takes hours of searching through PDFs and email. Commercial equivalents are in beta: Procore Assist (formerly Copilot) answers questions over RFIs, submittals, specs and drawings, and Autodesk Assistant does the same over specs, RFIs and schedule tasks. Both are tied to expensive platforms, so a self-hosted, open-source version is a real differentiator.
- **Project managers:** Fast status questions across modules ("open RFIs plus late activities on level 2").
- **Estimators:** Checking spec requirements against BOQ positions, which also feeds the validation rules.

## Implementation effort
**Medium.** Modules touched: `documents`, `erp_chat`, `core/vector_index.py`, plus a new `vector_adapter.py` in `rfi`, `meetings`, `transmittals`, `changeorders`, `submittals` and `schedule`.

Sketch:
1. **Chunk index.** Add an `oe_document_chunks` collection and a `DocumentChunkAdapter`. On the existing document-uploaded event, a background task extracts text per page (pymupdf, already present; Docling optional for tables and layout), splits it into roughly 500-token chunks, and stores `{document_id, page, chunk_no}` in the payload. Optionally, prepend an LLM-written chunk context (Anthropic "contextual retrieval") when an AI key is configured. Without a key it degrades gracefully to plain chunks.
2. **Correspondence adapters.** Each module ships a `vector_adapter.py` following the existing pattern and subscribes to its own create and update events. This keeps the "modules = plugins" rule intact.
3. **Hybrid retrieval.** Use LanceDB's built-in full-text index (Tantivy) with the RRF reranker. Qdrant has a comparable hybrid path.
4. **Citations.** Add a `search_project_knowledge` tool to `erp_chat/tools.py` that returns hits with `{module, id, page, snippet}`. The prompt in `erp_chat/prompts.py` requires every claim to cite a hit. The frontend renders citations as deep links.
5. **MCP (optional, later).** Expose the read-only tools through the official MCP Python SDK so Claude Desktop and other MCP clients can query a project.

## Building blocks
- **LanceDB** (Apache-2.0): embedded vector database with full-text search and hybrid rerankers. Already a dependency. https://lancedb.com/docs/search/hybrid-search
- **PyMuPDF / PyMuPDF4LLM** (AGPL-3.0, or commercial from Artifex): fast PDF-to-text and Markdown extraction. The license is compatible with this repo's AGPL core but matters for commercial builds. https://github.com/pymupdf/pymupdf4llm
- **Docling** (MIT code; bundled models carry their own licenses): layout-aware conversion of PDF and Office files with a `HybridChunker`. Heavier, so it fits as an optional module. https://github.com/docling-project/docling
- **pdfplumber** (MIT): already used here. Good for tables.
- **Anthropic Contextual Retrieval:** published technique plus cookbook. Vendor-reported 49-67% fewer retrieval failures with BM25 and reranking. https://www.anthropic.com/news/contextual-retrieval
- **MCP Python SDK** (MIT): for exposing project tools to external assistants. https://github.com/modelcontextprotocol/python-sdk
- **LanceDB MCP servers:** only community projects exist (for example `adiom-data/lance-mcp`). I could not verify one maintained under the lancedb organization, so it is better to build on the ERP's own tools than to adopt one.

## Priority: 5/5 — The vector, adapter and tool-calling layers already exist. Indexing document contents and correspondence and adding citations is a Medium job that turns the existing chat into a real "ask your project" feature that small firms cannot otherwise afford.

## Sources
- https://support.procore.com/products/online/user-guide/project-level/assist/about-assist
- https://support.procore.com/products/online/user-guide/project-level/copilot/about-copilot
- https://www.autodesk.com/blogs/construction/gcs-meet-autodesk-assistant-a-smart-tool-that-can-help-you-find-answers/
- https://www.anthropic.com/news/contextual-retrieval
- https://lancedb.com/docs/search/hybrid-search
- https://docs.lancedb.com/reranking.md
- https://github.com/pymupdf/pymupdf4llm
- https://arxiv.org/abs/2501.17887
- https://pypi.org/project/docling/
- https://github.com/modelcontextprotocol/python-sdk
- https://cdn.jsdelivr.net/gh/adiom-data/lance-mcp@main/README.md
