# 069. Voice input / dictation for field

## What it does
Lets site staff speak instead of type: a microphone button on long-text fields (daily report "work performed", delays, punch-list descriptions, RFI questions, inspection notes, safety observations) turns speech into text. A second step can have the existing AI module turn a free-form voice note ("poured slab level 2, 6 workers, crane down two hours") into structured fields (workforce, equipment, delay_hours), which the user reviews before saving. Three engine options:
- **Web Speech API** (`SpeechRecognition` / `webkitSpeechRecognition`): zero cost, no backend. Works in Chrome and partly in Safari. Not in Firefox. Audio usually goes to the browser vendor's cloud.
- **Server-side Whisper** (self-hosted faster-whisper / whisper.cpp, or a hosted API such as OpenAI `gpt-4o-mini-transcribe`): consistent quality across browsers and multilingual.
- **On-device Whisper** (Transformers.js + WebGPU, or whisper.cpp WASM): private and offline-capable. The cost is a large model download and slow transcription on low-end phones.

## Already in the codebase (with file paths)
- No speech or dictation code exists. A grep for `SpeechRecognition`, `MediaRecorder`, `getUserMedia`, `whisper` and `dictat` in `backend/app` and `frontend/src` finds nothing relevant.
- These text fields could take dictation: `backend/app/modules/fieldreports/models.py` (`work_performed`, `delays`, `notes`, `safety_incidents`), plus the punchlist, rfi, inspections and safety modules. Matching UI lives in `frontend/src/features/fieldreports/` and `frontend/src/features/punchlist/`.
- `backend/app/modules/ai/ai_client.py` already routes calls to Anthropic, OpenAI, Gemini and OpenAI-compatible providers (Groq, Mistral, OpenRouter), with user-supplied keys. It handles chat completions only, not audio, but the same key and config pattern can be reused for a transcription endpoint.
- i18n already covers 20 languages, so recognition language can follow the user's UI locale.

## Who it helps and how much
Mainly site foremen and supervisors who fill in daily logs on a phone with gloves on or in a hurry. Typing on a phone is the main reason daily reports end up empty or late. Dictation plus AI-to-structured-fields can cut report time a lot and makes the data more complete, which in turn helps the delay claims, change orders and EVM features. Estimators in the office gain less, though dictation is still handy for RFI and meeting notes. For a small firm the value is moderate-to-high: cheap to add, used every day.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Small to Medium overall.**
1. **Small (frontend only):** a shared `<DictationButton>` / `useDictation()` hook in `frontend/src/shared/ui` built on the Web Speech API. It feature-detects support, hides itself where unsupported, sets `lang` from the i18n locale, and appends text to the bound textarea. No new dependencies.
2. **Medium (backend fallback):** a `POST /api/v1/ai/transcribe` endpoint in the `ai` module. It accepts a `MediaRecorder` webm/opus blob and forwards it to the configured provider (OpenAI or Groq audio endpoints) or to an optional self-hosted faster-whisper service (a separate container, like `services/ai-service`). Store the audio in `core/storage` attached to the report so there is an audit trail.
3. **Medium (structuring):** a prompt in `ai/prompts.py` that maps a transcript onto the FieldReport schema and returns suggested values with confidence scores. Per the "AI-augmented, human-confirmed" principle, nothing is saved without review. Add validation rules too, for example flagging delay_hours > 0 when the delays text is empty.
4. Optional later: on-device Transformers.js Whisper as a lazy-loaded plugin module for offline sites.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- Web Speech API (MDN): https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API. Free, built into the browser. Support: https://caniuse.com/speech-recognition (Chrome yes, Safari partial, Firefox no).
- MediaRecorder API: https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder. Free, built into browsers.
- OpenAI Whisper model weights: https://github.com/openai/whisper. MIT.
- faster-whisper (CTranslate2, server-side Python): https://github.com/SYSTRAN/faster-whisper. MIT.
- whisper.cpp (C/C++, WASM build possible): https://github.com/ggml-org/whisper.cpp. MIT.
- Transformers.js (in-browser, WebGPU): https://github.com/huggingface/transformers.js. Apache-2.0. Demo app: https://github.com/xenova/whisper-web.
- OpenAI speech-to-text API: https://platform.openai.com/docs/guides/speech-to-text. Pay per use. Third-party aggregators report about $0.003/min for gpt-4o-mini-transcribe and $0.006/min for whisper-1 / gpt-4o-transcribe. Check https://openai.com/api/pricing before budgeting.
- Groq hosted Whisper (OpenAI-compatible): https://console.groq.com/docs/speech-to-text. Paid with a free tier; the provider is already in `ai_client.py`.
- MCP servers: none needed. Dictation is a UI input feature, not an agent tool, and I did not verify any MCP server worth recommending for it.

## Priority: 3/5 — Cheap Web Speech quick win for field logs; Whisper fallback and AI structuring add value but depend on mobile and field usage maturing first.

## Sources
- https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
- https://caniuse.com/speech-recognition
- https://web-platform-dx.github.io/web-features-explorer/features/speech-recognition
- https://platform.openai.com/docs/guides/speech-to-text
- https://costgoat.com/pricing/openai-transcription
- https://github.com/openai/whisper
- https://github.com/SYSTRAN/faster-whisper
- https://github.com/ggml-org/whisper.cpp
- https://github.com/huggingface/transformers.js
- https://github.com/xenova/whisper-web
- https://console.groq.com/docs/speech-to-text
