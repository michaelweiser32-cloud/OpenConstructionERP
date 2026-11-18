# 048. WhatsApp Business Platform and Telegram bots for field crews

## What it does
Lets site crews work with the ERP from the messenger already on their phones, with no app install and no login screen. Messages go both ways:
- **Outbound:** alerts for RFI answers, inspections that are due, punch items assigned, schedule changes and daily-report reminders.
- **Inbound:** a foreman sends a photo, voice note, GPS location or short text such as "poured 12 m3 slab B2". The bot files it as a draft field report, punch item, safety observation or document and asks the sender to confirm.

Telegram uses the free Bot API, with webhooks, inline keyboards and Mini Apps. WhatsApp uses Meta's Cloud API, with webhooks, templates and media download.

## Already in the codebase (with file paths)
- `backend/app/modules/integrations/telegram.py`: **outbound only**. It sends one HTML `sendMessage` using a stored `bot_token` and `chat_id`. There is no webhook receiver, update handling, file download or user linking.
- `backend/app/modules/integrations/whatsapp.py`: **outbound only**. It sends a template message through `graph.facebook.com/v20.0`. Graph versions expire about two years after release, so check whether v20.0 still works and bump it if needed.
- `backend/app/modules/integrations/router.py` (about line 226): the WhatsApp "test" endpoint returns "requires Meta Business verification. Coming soon."
- `backend/app/modules/integrations/models.py` and `schemas.py`: configs are stored per integration type, as `{bot_token, chat_id}` or `{phone_number_id, access_token, to_phone}`.
- `backend/app/modules/erp_chat/tools.py`: has AI tool-calling that could serve as the "brain" behind a chat bot. It is not yet connected to any messenger.
- `backend/app/modules/fieldreports/`, `punchlist/`, `safety/`, `documents/`: these are the places inbound messages would be saved. None of them accept messenger input today.

**Gap:** an inbound channel (webhook, signature check, media fetch), mapping each phone number or Telegram user to an ERP user and project, a conversation state machine, and confirm-before-save flows.

## Who it helps and how much
- **High value for small contractors.** Crews already coordinate on WhatsApp in most of Europe, Latin America, the Middle East and India, and Telegram is common in Eastern Europe and Central Asia. Getting field data in costs only a chat message, which is the most practical way to make daily reports and photo documentation actually happen.
- Estimators and PMs get timestamped, geotagged evidence attached to the right project, which helps with change orders and disputes.
- The office gets push notifications without paying for Slack or Teams seats.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium.** Telegram alone is Small to Medium. WhatsApp adds Meta business verification, template approval and per-message cost tracking.

The work is a new sub-package or module, `field_messaging`, that depends on `oe_integrations`, `oe_fieldreports`, `oe_punchlist` and `oe_documents`:
1. **Webhook routes.** `POST /api/v1/field_messaging/telegram/{config_id}` checks Telegram's `X-Telegram-Bot-Api-Secret-Token` header. `GET` and `POST /whatsapp/{config_id}` handle Meta's `hub.challenge` handshake and its `X-Hub-Signature-256` HMAC.
2. **Identity link.** A table maps a phone number or Telegram user ID to a user and an active project. Linking uses a one-time code sent from the user's profile page.
3. **Media.** Photos are fetched through Telegram `getFile` or the WhatsApp media ID, then stored in `core/storage`. WhatsApp media URLs expire in about 5 minutes, so download them right away.
4. **Intent parsing.** Simple slash or keyword commands come first. `erp_chat` tools can optionally extract fields. Following the AI-augmented, human-confirmed principle, the bot replies with a summary and Confirm / Edit buttons and only then creates the record.
5. **Validation.** Each draft goes through the validation engine before it is saved.
6. **Outbound.** Subscribe to the event bus (for example `punchlist.item_assigned`) and reuse the existing senders.
7. **i18n.** All bot replies go through the i18n files, and the user's language is detected from the messenger's language code.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **Telegram Bot API** (https://core.telegram.org/bots/api): free and unlimited, with a 20 MB bot download limit. The changelog lists 10.3 (Aug 2026), and news reports mention 10.4.
- **aiogram** (https://github.com/aiogram/aiogram): MIT, async, has webhook support built in. It is a good fit for FastAPI, or you can call the API directly with `httpx` as the code already does.
- **python-telegram-bot** (https://github.com/python-telegram-bot/python-telegram-bot): LGPLv3.
- **WhatsApp Cloud API** (https://developers.facebook.com/docs/whatsapp/cloud-api): free API access, but billed **per message** since July 2025. Marketing, utility and authentication templates are charged at country rates. Free service replies within the 24-hour window are reported to become billable on **1 Oct 2026**. That comes from third-party summaries; confirm it on Meta's rate card.
- **Media API** (https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media): describes the flow of media ID, then URL, then authenticated GET.
- **MCP servers:** I found no official WhatsApp or Telegram MCP server. Community projects such as `lharries/whatsapp-mcp` (MIT, logs into a *personal* account via whatsmeow) and Telegram MTProto servers (`chaindead/telegram-mcp`, `overpod/mcp-telegram`) act as a user account, not a business bot. They may break the platform's terms and are unsuitable as a product integration. A better approach is to expose the ERP's own MCP or tools and keep the messengers as plain webhooks.

## Priority: 4/5 — chat-first field capture fits small crews best and most of it is already built, but WhatsApp onboarding friction and new per-message costs argue for shipping Telegram plus a WhatsApp beta first.

## Sources
- https://core.telegram.org/bots/api
- https://core.telegram.org/bots/api-changelog
- https://github.com/aiogram/aiogram
- https://docs.python-telegram-bot.org/
- https://developers.facebook.com/docs/whatsapp/pricing
- https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media
- https://developers.secure.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
- https://www.wati.io/en/blog/whatsapp-business-api-pricing-changes-2026-what-august-and-october-actually-cost-you/
- https://baat.ai/blog/whatsapp-pricing-per-message
- https://mcpservers.org/servers/rohit678/whatsapp-mcp
- https://enterprisedna.co/directories/mcp/lharries-whatsapp-mcp

Note: I could not open developers.facebook.com or core.telegram.org from the research environment (the network blocked them). Facts from those sites come from search-result snippets of the official pages and should be checked again before implementation.
