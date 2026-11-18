# 066. LLM provider options: Anthropic, OpenAI, Gemini, Mistral, OpenRouter, local Ollama/vLLM, and their pricing tradeoffs

## What it does
Decides which large-language-model backends power the ERP's AI features: BOQ generation from text or photos, the ERP chat assistant with tool calling, classification, and document extraction. It also covers how a small firm chooses between cost, quality, privacy and running offline. For a small estimator the main levers are: (a) bring-your-own-key for hosted frontier models, (b) one aggregator key (OpenRouter) that reaches many models, and (c) a local model (Ollama/vLLM) when data must stay on-premise or the AI budget is near zero.

## Already in the codebase (with file paths)
Coverage is already broad. The gaps are specific.
- `backend/app/modules/ai/ai_client.py`: native httpx callers for Anthropic, OpenAI and Gemini, with no SDK dependency. An OpenAI-compatible table (`_OPENAI_COMPAT_CONFIG`) holds fixed URLs for OpenRouter, Mistral, Groq, DeepSeek, Together, Fireworks, Perplexity, Cohere, AI21 and xAI. `resolve_provider_and_key()` maps the model name to the provider key using keyword matching.
- `backend/app/modules/ai/models.py`: per-user, Fernet-encrypted key columns for about 17 providers; `tokens_used` is logged per job.
- `backend/app/config.py`: environment-level fallback keys.
- `backend/app/modules/erp_chat/service.py`: native tool calling only for `anthropic` and `openai`. Other providers fall back to plain text.

**Gaps:**
1. There is no local provider: no configurable `base_url`, so Ollama, vLLM, LM Studio or llama.cpp cannot be used.
2. The default models are hard-coded and dated (e.g. `claude-sonnet-4-20250514`, `gpt-4o`, `gemini-2.0-flash`).
3. Token counts are stored, but there is no cost-in-currency estimate and no per-tenant budget cap.
4. There is no prompt caching or batch mode, although both providers offer large discounts on repeated system prompts.
5. Tool calling is not available through OpenAI-compatible providers, even though OpenRouter, Mistral and Ollama all support the `tools` parameter.

## Who it helps and how much
- **Small firm, no IT staff:** benefits most from a single OpenRouter key (one bill, many models, free models for trials) or a low-cost "Flash/mini" tier. AI cost for occasional estimating is likely to be small. Verify on the official pricing pages; third-party aggregators disagree.
- **Privacy-sensitive or DACH/EU firms:** a local Ollama on a workstation GPU, or Mistral (EU-hosted), avoids sending tender documents to US clouds.
- **Power estimators:** frontier models (Claude/GPT/Gemini Pro tiers) give better BOQ structure and vision takeoff, at roughly 10-50x the per-token price of budget tiers.

Impact: **High.** Every AI feature depends on this layer. Local support also fits the project's "lightweight, runs on a VPS" philosophy.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Small-Medium**, in the `ai` and `erp_chat` modules.
- Add a `custom_openai` provider: user-supplied `base_url` plus an optional key and model name, stored in `AISettings`. Presets: Ollama `http://localhost:11434/v1`, vLLM `http://host:8000/v1`. This reuses `call_openai_compatible()` unchanged.
- Generalise the `erp_chat` tool loop to send OpenAI-format `tools` to any OpenAI-compatible provider.
- Add a small `pricing.json`, a data file editable without a code change, holding $/M input and output per model. Use it to compute `cost_estimate` next to `tokens_used`, and fire an event (`ai.budget_exceeded`) via the event bus when a configurable monthly cap is hit.
- Move default model IDs to config, and add an Anthropic `cache_control` flag on the long system prompts.
- Validation rule (per project convention): mark AI-generated BOQ positions with `source=ai` and a confidence score, with human review required.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Ollama:** OpenAI-compatible `/v1/chat/completions` with tools, streaming and vision. MIT license, free. https://docs.ollama.com/api/openai-compatibility
- **vLLM:** high-throughput OpenAI-compatible server for GPU hosts. Apache-2.0. https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
- **OpenRouter:** one key for hundreds of models. Inference is billed at the provider's list price, plus a fee on credit purchases (reported as about 5.5%). Free models are rate-limited (reported as 50 requests/day, rising to 1,000/day after a $10 credit purchase). https://openrouter.ai/pricing
- **LiteLLM:** optional proxy/SDK that normalises over 100 providers and tracks spend. MIT license (core). Note that it is a heavy dependency; the existing httpx client is lighter. https://docs.litellm.ai/docs/providers/ollama
- **Official pricing pages** (pay-per-token, no subscription). Anthropic and OpenAI offer batch and prompt-cache discounts. Gemini has a free tier, whose data terms differ from the paid tier.
  - https://www.anthropic.com/pricing
  - https://openai.com/api/pricing/
  - https://ai.google.dev/gemini-api/docs/pricing
  - https://mistral.ai/pricing

**Pricing caveat:** the official pages could not be fetched from this research environment. Aggregators (BenchLM, CostBench) show budget tiers from about $0.05-0.30/M input tokens and frontier tiers from about $2.50-5/M input and $15-25/M output, with conflicting figures. Specific numbers must be checked on the official pages before shipping a `pricing.json`.

**MCP:** no provider-specific MCP server is needed. MCP is for exposing ERP tools to LLM clients, which is covered by other topics.

## Priority: 4/5 — the multi-provider plumbing exists, and adding local/custom base URLs, tool calling for compatible providers, and cost tracking is cheap and unlocks private, near-zero-cost AI for small firms

## Sources
- https://docs.ollama.com/api/openai-compatibility
- https://registry.ollama.ai/blog/tool-support
- https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
- https://openrouter.ai/pricing
- https://openrouter.ai/docs/faq
- https://mistral.ai/en/pricing
- https://www.anthropic.com/pricing
- https://openai.com/api/pricing/
- https://ai.google.dev/gemini-api/docs/pricing
- https://docs.litellm.ai/docs/providers/ollama
- https://benchlm.ai/llm-pricing
- https://www.costbench.com/software/llm-api-providers/
