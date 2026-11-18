# 064. LLM Estimate Generation from Scope Description / Photos into BOQ (Human-Confirmed)

## What it does
An estimator types a short scope ("re-roof 180 m2 pitched roof, replace battens, new gutters") or uploads one or more site photos, and an LLM drafts a structured BOQ: positions with description, unit, quantity, unit rate, classification code and a per-line confidence score plus the assumption behind it. The draft is never written straight into a live BOQ: the user reviews it line by line (accept / edit / reject / swap for a cost-database match), and only accepted lines become positions with `source=ai_estimate`, followed by an automatic validation pass.

## Already in the codebase (with file paths)
Most of the pipeline already exists, so the remaining work is about quality and trust, not a new module.
- `backend/app/modules/ai/router.py`: `/quick-estimate/` (text), `/photo-estimate/` (single image, 10 MB), `/file-estimate/` (PDF/Excel/CAD/image), `/estimate/{job_id}/enrich/` (vector and text match against the cost DB), `/estimate/{job_id}/create-boq/`.
- `backend/app/modules/ai/ai_client.py`: multi-provider calls (Anthropic, OpenAI, Gemini and OpenAI-compatible providers). It uses one image per call and turns the model's free text into JSON with the regex helper `extract_json()`. The default model IDs are hard-coded and dated (`claude-sonnet-4-20250514`, `gpt-4o`, `gemini-2.0-flash`).
- `backend/app/modules/ai/prompts.py`: `TEXT_ESTIMATE_PROMPT` and `PHOTO_ESTIMATE_PROMPT`. `models.py` has `AIEstimateJob`, which persists the jobs.
- `backend/app/modules/ai/service.py` `create_boq_from_estimate`: copies every item into a new draft BOQ with a hard-coded `confidence="0.7"`. The `EstimateItem.confidence` schema field is ignored, and the user cannot choose which items to import.
- `frontend/src/features/ai/QuickEstimatePage.tsx`: a results table that shows enrichment matches, and a save dialog with a project picker and BOQ name.
- `backend/app/modules/erp_chat/tools.py`: `handle_create_boq_item` and `handle_search_cwicr_database` could be reused for a conversational version.

**Gaps:**
1. No schema-guaranteed output. It relies on regex JSON extraction.
2. The confidence score is fake (always 0.7).
3. No per-line accept/reject step before import.
4. Cost-DB grounding happens only after generation, not during it.
5. Only one photo per call, and there is no request to the user for a reference dimension.
6. No automatic `boq_quality` validation run after import.
7. The model IDs are stale and not configurable per tenant.

## Who it helps and how much
This brings the most value to small contractors and one- or two-person estimating offices doing repair, renovation and small new-build work. A first-pass budget estimate takes them hours, and they have no drawings to run takeoff on. A grounded draft in about a minute, which the user then corrects, could cut early-stage pricing time substantially; this is an estimate, not a measured result. Photo-only quantities are inherently rough, and commercial tools in this space position them as ballpark quotes. That makes human confirmation and visible assumptions essential to trust (CLAUDE.md principle 7).

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** It touches `ai` (main), `boq` (bulk insert with per-line metadata), `costs` and `vector` (grounding) and `validation` (post-import run). No new module is needed.
1. Define an `EstimateDraft` Pydantic schema (items, unit enum, confidence, assumptions, `cost_item_ref`). Send it as native structured output where the provider supports it: Anthropic `output_config.format` or strict tools, OpenAI `json_schema` strict, Ollama `format`. Keep `extract_json` only as a fallback.
2. Grounding, two-step: the LLM first proposes the scope breakdown. A vector search in `costs` then fetches the top-k rates per line. A second LLM call picks or adjusts rates and must cite `cost_item_id`, or flag "no match" and lower its confidence.
3. Multi-image input, plus an optional reference measurement field the user fills in to anchor scale.
4. Change `CreateBOQFromEstimateRequest` to accept `accepted_items[]` with any user edits. Store the real per-line confidence and the assumptions in `metadata`.
5. Publish an `ai.estimate.imported` event. The `validation` module subscribes and runs `boq_quality`.
6. Move the model IDs into `AISettings` and make them configurable per tenant.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Anthropic structured outputs and strict tool use** (https://platform.claude.com/docs/en/build-with-claude/structured-outputs). Stable on current models. Requires `additionalProperties: false` and does not support numeric min/max constraints. Pay-per-token.
- **OpenAI Structured Outputs** (https://platform.openai.com/docs/guides/structured-outputs). `json_schema` with `strict: true`. Pay-per-token.
- **Ollama structured outputs with vision models** (https://ollama.com/blog/structured-outputs). Local inference with no data leaving the server. MIT license. Useful for privacy-sensitive tenants.
- **Instructor** (https://github.com/567-labs/instructor). Pydantic-validated LLM outputs with retries. MIT license. This is an optional dependency: the in-house clients plus Pydantic are probably enough.
- The existing cost-database vector search (pgvector/Qdrant) and the CWICR data are already in the repo. Nothing new is needed.
- **MCP:** I found no verified public MCP server for construction estimating. The existing `erp_chat` tools could later be exposed as an MCP server, which is a separate topic.
- **Market reference:** commercial photo-to-quote and AI-estimating apps sell at roughly 30 to 300 USD per user per month, according to third-party roundups (https://thedigitalprojectmanager.com/tools/best-ai-estimating-software/). These figures are unverified against vendor pages.

## Priority: 4/5 — the feature already exists end-to-end, so cheap fixes (schema output, real confidence, per-line review, cost-DB grounding) turn a demo into a trustworthy daily tool for small firms
Not 5: photo-based quantities stay rough by nature, and drawing-based takeoff remains the accuracy path.

## Sources
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- https://aws.amazon.com/blogs/machine-learning/structured-outputs-for-anthropic-claude-models-on-amazon-bedrock/
- https://platform.openai.com/docs/guides/structured-outputs
- https://ollama.com/blog/structured-outputs
- https://github.com/567-labs/instructor
- https://thedigitalprojectmanager.com/tools/best-ai-estimating-software/
- https://servicebusinessacademy.org/best-photo-to-quote-software-contractors-2026/
