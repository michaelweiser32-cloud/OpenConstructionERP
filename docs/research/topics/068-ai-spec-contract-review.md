# 068. AI Spec and Contract Review (scope extraction, risk clauses, exclusions)

## What it does
The user uploads a tender package (specification PDF, contract or subcontract terms, scope letter). The system parses it and an LLM produces three outputs, each linked to a page or paragraph citation:
1. **Scope items.** Work packages, materials, standards and testing requirements, drafted as BOQ-ready positions or requirements.
2. **Risk clauses.** Liquidated damages, pay-when-paid terms, indemnity, retention, uncapped liability, short notice periods, termination for convenience and warranty length. Each is flagged with a severity and a confidence score.
3. **Exclusions and assumptions.** Items the estimator should exclude or qualify in the bid, plus gaps where the spec and the BOQ disagree.

Every AI suggestion needs a human to accept or reject it before it is applied. This follows the project rule "AI-augmented, human-confirmed".

## Already in the codebase (with file paths)
- **Multi-provider LLM client.** `backend/app/modules/ai/ai_client.py` already calls Anthropic, OpenAI, Gemini and OpenAI-compatible endpoints. `backend/app/modules/ai/router.py` has `file_estimate` (a PDF goes to a BOQ draft through `boq.router._extract_from_pdf`) and an `advisor_chat`.
- **Requirements module.** `backend/app/modules/requirements/` (models `RequirementSet`, `Requirement`, `GateResult`) stores EAC requirement triplets and runs quality gates. It has bulk-add endpoints but no extraction from documents. It is the natural place to store spec-derived scope.
- **Risk register.** `backend/app/modules/risk/models.py` (`RiskItem`) has no link to contract clauses and no AI ingestion.
- **Document parsing and search.** `backend/app/modules/documents/service.py` already uses pdfplumber (`split_pdf_to_sheets`). `documents/vector_adapter.py` embeds documents into `core/vector_index.py`, so retrieval over specs is partly in place.
- **Gap.** There is no clause taxonomy and no contract or spec review workflow. Nothing produces an exclusions or qualifications list, and nothing links extracted items back to tender, BOQ or risk records.

## Who it helps and how much
- **Small general contractors and subcontractors.** They bid many jobs without in-house legal or QS staff, and a 300-page spec often gets skimmed. A first-pass review that flags LDs, pay-when-paid and retention terms, and lists items "by others", cuts down missed scope and onerous terms that go unpriced. **Value: High.**
- **Estimators.** Scope extraction feeds BOQ positions and the requirements gates directly, and an exclusions list can be pasted into the bid letter (`tendering` / `rfq_bidding`).
- **Limitation.** The output is decision support, not legal advice. The UI must say so.

## Implementation effort
**Medium.** Most of the plumbing already exists. A new module `oe_doc_review` (depends on `oe_ai`, `oe_documents`, `oe_requirements`, `oe_risk`) would work like this:
- **Pipeline.** Parse with pdfplumber or Docling into sections. Run chunked LLM calls through `ai_client.call_ai`, with a JSON schema per clause type and a YAML clause taxonomy (an i18n-able rule set).
- **Model.** A `ReviewFinding` table (type = scope / risk / exclusion, severity, confidence, page or offset citation, status = pending / accepted / rejected).
- **Accept actions.**
  - A scope finding becomes a `Requirement` or a draft BOQ position.
  - A risk finding becomes a `RiskItem`.
  - An exclusion becomes a tender qualifications list.
- **Validation and events.** A validation rule `contract_review.unreviewed_high_risk` blocks bid submission while high-severity findings are still pending. The module publishes events (`doc_review.finding_accepted`) and exposes an `erp_chat` tool, "summarize risks in this contract".
- **Native PDF citations.** Where a provider supports them (Anthropic Citations), these give page-anchored evidence. For other providers, fall back to text offsets.

## Building blocks
- **Docling** (MIT). Layout-aware PDF parsing with table structure. https://github.com/docling-project/docling
- **docling-mcp** (MIT). An MCP server for document conversion that can be exposed to agents. https://github.com/docling-project/docling-mcp
- **pdfplumber** (MIT). Already used in the repo. https://github.com/jsvine/pdfplumber
- **CUAD dataset** (CC BY 4.0). 41 commercial clause categories over 510 contracts. A useful seed for the taxonomy and for evaluation, though it is not construction-specific. https://huggingface.co/datasets/theatticusproject/cuad
- **Claude PDF support and Citations API** (paid, priced per token). https://platform.claude.com/docs/en/build-with-claude/pdf-support and https://platform.claude.com/docs/en/build-with-claude/citations
- **Academic prior art.** BERT-based detection of risk clauses in construction specifications (Moon, Chi, Im, *Automation in Construction*, 2022). An NLP/ML review of construction contract clauses for risk, rights and responsibility (2025).
- **Not found.** I could not verify any open-source construction-specific clause model or construction contract-review MCP server. Commercial tools exist, but their APIs are not public or could not be verified.

## Priority: 4/5 — high bid-risk value for small firms, and it mostly reuses the existing ai, documents, requirements and risk modules; legal-liability framing and accuracy evaluation keep it from 5.

## Sources
- https://github.com/docling-project/docling
- https://arxiv.org/abs/2408.09869
- https://github.com/docling-project/docling-mcp
- https://docling-project.github.io/docling/usage/mcp/
- https://github.com/jsvine/pdfplumber
- https://huggingface.co/datasets/theatticusproject/cuad
- https://arxiv.org/abs/2103.06268
- https://platform.claude.com/docs/en/build-with-claude/pdf-support
- https://platform.claude.com/docs/en/build-with-claude/citations
- https://open.metu.edu.tr/bitstream/handle/11511/113696/1-s2.0-S0166361525000168-main.pdf
- https://www.mastt.com/blogs/ai-contract-analysis
