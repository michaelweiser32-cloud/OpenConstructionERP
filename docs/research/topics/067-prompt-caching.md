# 067. Prompt caching, batch APIs and model routing to cut LLM API cost

## What it does
A set of techniques that reduce the cost of each AI feature without changing what it does for the user:
- **Prompt caching**: the large prefix that repeats on every call (system prompt, tool definitions, CWICR/catalogue context) is cached by the provider. Later reads are billed far below the normal input price. On Anthropic, cache reads cost 0.1x the base input price and caching is turned on with `cache_control`. OpenAI caches prompts of 1024 tokens or more automatically. Gemini 2.5+ supports implicit and explicit context caching.
- **Batch APIs**: jobs that do not need an answer straight away are billed at 50% of normal price. Examples are overnight re-classification of a cost database, bulk BOQ description cleanup and translating positions into the 20 UI languages. Anthropic's docs say caching discounts stack with the batch discount. For OpenAI, the sources conflict on whether they stack, so check its current docs before relying on it.
- **Model routing**: easy requests (titles, simple lookups, connectivity tests) go to a cheap model and hard ones (BOQ generation, takeoff reasoning) go to a strong one. The router can be a set of rules or a learned router such as RouteLLM.
- **Cost accounting**: record the token types (input, output, cache write, cache read) and the price of each, so a small firm can see what it spends on AI per project.

## Already in the codebase (with file paths)
- `backend/app/modules/ai/ai_client.py`: a multi-provider client built on httpx (Anthropic, OpenAI, Gemini, OpenRouter, Mistral, Groq, DeepSeek). Model IDs are hard-coded constants (for example `ANTHROPIC_MODEL = "claude-sonnet-4-20250514"`). It sends no `cache_control`, does not call the batch endpoint and does no routing.
- `backend/app/modules/erp_chat/service.py`: the tool-calling chat. It sends the same `SYSTEM_PROMPT` and `TOOL_DEFINITIONS` on every turn, which is an ideal candidate for caching, but nothing marks them as cacheable. `preferred_model` is read from settings and then ignored (`pass  # Keep default`).
- `backend/app/modules/ai/models.py` and `backend/app/modules/erp_chat/models.py` store a single `tokens_used` integer. Input, output and cache tokens are added together, so the system cannot work out what a call cost.
- No batch job, no semantic cache and no per-tenant AI budget.

**Gap**: the provider layer is in place, but none of the cost levers are used.

## Who it helps and how much
Small estimating firms using their own API key (BYOK) pay for every token. In chat, the system prompt and tool schema make up most of the input on every turn, so caching that prefix could cut input cost on later turns by up to about 90% on Anthropic. Moving bulk jobs to batch halves their cost. Routing trivial calls to a smaller model cuts cost further. Together these levers can make AI features affordable at small-firm volume. The savings depend on how often the cache is hit, and the exact gain has not been measured for this codebase.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch)
**Small to Medium**, mostly in the `ai` module, with `erp_chat` using it.
1. Small: add `cache_control: {"type": "ephemeral"}` breakpoints on the system prompt and the last tool definition in `_call_anthropic`. Keep prompt prefixes stable (no timestamps) so OpenAI and Gemini get automatic cache hits.
2. Small: honour `preferred_model`. Add a routing table in `ai/ai_client.py` that maps task type (`classify`, `chat`, `boq_generate`, `ping`) to a model tier, configurable per tenant.
3. Medium: add a `usage` JSON column next to `tokens_used` and a price table in a module data file, then show a cost-per-project widget in reporting.
4. Medium: add a `ai_batch` job runner (in-process for dev, Celery when Redis is present). It submits bulk jobs to the Anthropic Message Batches or OpenAI Batch endpoints, polls for results and publishes an event when they finish. Results land as *suggestions* for human review, following the AI-augmented, human-confirmed principle.
5. Optional: put a LiteLLM proxy in front of the client for fallbacks, spend tracking and budgets. It is external and adds no dependency to core.

## Building blocks
- Anthropic prompt caching and Message Batches: pay-as-you-go, cache read 0.1x, batch 50% off. https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Anthropic pricing (batch and cache multipliers): https://platform.claude.com/docs/en/about-claude/pricing
- OpenAI prompt caching (automatic, 1024 tokens or more) and Batch API (50% off, results within 24 hours): https://openai.com/index/api-prompt-caching and https://developers.openai.com/cookbook/examples/prompt_caching101
- Gemini implicit and explicit context caching: https://developers.googleblog.com/en/gemini-2-5-models-now-support-implicit-caching/ and https://cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview
- LiteLLM: a proxy and router with fallbacks and spend tracking. The core is MIT, with an enterprise folder under a commercial licence. Third-party reports mention a 2026 PyPI supply-chain incident, so pin versions. https://github.com/BerriAI/litellm
- RouteLLM (lm-sys): learned cost/quality routers, Apache-2.0. The paper reports more than 2x cost savings. https://github.com/lm-sys/RouteLLM and https://lmsys.org/blog/2024-07-01-routellm
- I did not find a dedicated MCP server for LLM cost optimisation, and none is needed. This is a change inside the provider client.
- Not verified: GPTCache (semantic cache). Its licence was not confirmed in this research.

## Priority: 4/5. The changes are cheap, contained in the ai module and add no new dependencies. They directly lower running cost for BYOK small firms, and the caching fix is close to a one-line change.

## Sources
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://platform.claude.com/docs/en/about-claude/pricing
- https://openai.com/index/api-prompt-caching
- https://developers.openai.com/cookbook/examples/prompt_caching101
- https://community.openai.com/t/can-batch-api-work-with-prompt-caching/1044983
- https://developers.googleblog.com/en/gemini-2-5-models-now-support-implicit-caching/
- https://cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview
- https://github.com/lm-sys/RouteLLM
- https://arxiv.org/html/2406.18665v3
- https://lmsys.org/blog/2024-07-01-routellm
- https://github.com/BerriAI/litellm
