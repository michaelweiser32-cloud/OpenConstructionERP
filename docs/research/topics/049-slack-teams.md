# 049. Slack and Microsoft Teams integration (notifications, slash commands, approvals)

## What it does
Pushes ERP events (RFI answered, change order submitted, invoice awaiting approval, validation errors on a BOQ, tender deadline) into the chat tool a small firm already lives in. It also lets users act from the chat: look up a project or BOQ total with a slash command, and approve or reject a change order, invoice or submittal with a button on the message. Every action is recorded in the audit log under the ERP user it maps to.

## Already in the codebase (with file paths)
- `backend/app/modules/integrations/slack.py`: one-way Block Kit post to a Slack **Incoming Webhook**.
- `backend/app/modules/integrations/teams.py`: one-way Adaptive Card post in `message/attachments` format. The docstring still says "Incoming Webhook", but Microsoft has retired Office 365 connectors, so users must now paste a **Workflows (Power Automate) webhook** URL. The payload format looks compatible, but nobody has tested it against a Workflows URL yet.
- `backend/app/modules/integrations/models.py`: `IntegrationConfig` with `integration_type`, `config`, an `events` list and `project_id`; also `WebhookEndpoint`/`WebhookDelivery` for generic signed webhooks.
- `backend/app/modules/integrations/router.py`: CRUD for configs and a `test` endpoint.
- `frontend/src/features/integrations/IntegrationsPage.tsx`: settings UI.
- **Gap:** nothing outside the module calls `send_slack_notification`, `send_teams_notification` or `WebhookService.dispatch_event`. The `events` filter is stored but no event-bus subscriber uses it, so notifications only fire on "test". There is no inbound endpoint for commands or buttons, no request-signature check, no mapping from Slack/Teams users to ERP users, and no approval round-trip.

## Who it helps and how much
- Estimators, PMs and site leads at firms with 2-30 people who already use Slack or Teams and rarely open the ERP. They get timely alerts without email noise.
- Owners and approvers: one-tap approvals on a phone shorten change-order and invoice cycles. This is a real cash-flow benefit for small contractors.
- Value is **High** once events are wired. Slash commands are nice to have; approvals are the main addition.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium**, in `integrations`, plus hooks into `notifications`, `changeorders`, `finance`, `submittals` and `core/events`.
1. **Small, do first:** register an event-bus subscriber in `integrations` (for example `events.py`, loaded by the module loader). It matches `IntegrationConfig.events` and `project_id`, sends through the right connector, and logs to `WebhookDelivery`. Rename the Teams setup text to Workflows and add i18n keys.
2. **Slack app (optional):** add `POST /api/v1/integrations/slack/events`, `/slack/commands` and `/slack/interactivity`. Verify the `X-Slack-Signature` HMAC (stdlib `hmac`, no SDK needed) and answer within 3 s. Store the bot token encrypted via `core/crypto.py`. Add `ChatIdentityLink` (chat user id to ERP user id).
3. **Approvals:** buttons carry `{entity_type, entity_id, action, nonce}`. The handler checks the RBAC permission of the linked user (`core/permissions.py`), calls the owning module's service and writes `core/audit`. Then it updates the message so nobody can approve twice. No action ever auto-applies an AI suggestion.
4. **Teams bot (Large, defer):** requires an Azure Bot registration, an app manifest and `Action.Execute` Universal Actions. Workflows webhooks only post messages; they cannot send button clicks back to the ERP.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- Slack Incoming Webhooks and Block Kit (free, already used): https://api.slack.com/messaging/webhooks
- Bolt for Python, slackapi/bolt-python (MIT), handles slash commands and interactivity. It is optional because signature checks fit in the stdlib: https://github.com/slackapi/bolt-python
- Slack free plan allows at most 10 apps, so a custom ERP app uses one slot: https://slack.com/help/articles/115002422943
- Official Slack MCP server: hosted, OAuth, needs admin approval, reported GA in 2026. It lets an AI client read and post in Slack; it does not replace a server-side bot. https://docs.slack.dev/ai/slack-mcp-server/
- Teams Workflows webhooks, the replacement for retired O365 connectors (included with Microsoft 365): https://mc.merill.net/message/MC1181996
- Microsoft Teams SDK (Python) with Adaptive Card `Action.Execute`: https://microsoft.github.io/teams-sdk/python/in-depth-guides/adaptive-cards/executing-actions
- Work IQ Teams MCP server (`mcp_TeamsServer`): preview, needs Microsoft 365 Copilot licences and admin consent, so it is not realistic for small firms: https://learn.microsoft.com/en-za/microsoft-copilot-studio/mcp-teams-work-iq

## Priority: 4/5 — the connectors exist but are never triggered, and wiring them to the event bus is cheap; Slack approvals add real value, while Teams interactivity can wait.

## Sources
- https://api.slack.com/messaging/webhooks
- https://github.com/slackapi/bolt-python
- https://slack.com/help/articles/115002422943
- https://api.slack.com/pricing
- https://docs.slack.dev/ai/slack-mcp-server/
- https://mc.merill.net/message/MC1181996
- https://office365itpros.com/2026/09/18/teams-workflows-updates/
- https://microsoft.github.io/teams-sdk/python/in-depth-guides/adaptive-cards/executing-actions
- https://learn.microsoft.com/en-za/microsoft-copilot-studio/mcp-teams-work-iq
