# 095. Notifications (in-app, email, web push, digests, user preferences)

## What it does
Tells each user, on the channel they choose, when something needs them: an RFI assigned or overdue, a submittal returned, a change order to approve, a tender deadline, a failed validation run. Layers: an in-app bell and inbox, immediate email, web push through the installed PWA, and daily or weekly digests with per-user, per-event channel preferences and quiet hours.

## Already in the codebase (with file paths)
- `backend/app/modules/notifications/`: a complete in-app module. It has the `Notification` model with i18n `title_key`/`body_key`/`body_context`, `action_url` and `is_read` (`models.py`). It supports create, notify_users, list, unread count, mark read, mark all read and `delete_old` (`service.py`), and the matching REST endpoints (`router.py`).
- `backend/app/modules/notifications/events.py`: only **4** event-bus subscribers are wired: `boq.boq.created`, `meeting.action_items_created`, `bim_hub.element.deleted` and `cde.container.state_transitioned`. RFI, submittals, change orders, tendering, punch list and validation do not notify yet.
- `backend/app/core/email/`: a pluggable email layer with `smtp`, `console`, `noop` and `memory` backends plus templates. Today it only sends password-reset and integration emails (`modules/integrations/email_service.py`).
- `backend/app/modules/integrations/`: webhooks and chat channels (Slack, Teams, Telegram and others).
- `frontend/src/shared/ui/NotificationBell.tsx`: the bell polls every 30 s (`refetchInterval: 30_000`).
- **Gaps**:
  - The manifest promises "per-user preferences", but no preferences model or endpoint exists.
  - No notification is ever routed to email.
  - There is no digest scheduler.
  - There is no web push: no service worker push handler, no VAPID keys, no subscription table.
  - Events from most business modules are not covered.

## Who it helps and how much
Small-firm estimators and project managers juggle many projects and are often on site. Missed RFI, submittal and bid deadlines cost delays, claims and lost tenders, and today users must open the app to see anything. Email plus a daily digest is the biggest gap, web push serves field users, and preferences prevent alert fatigue. **Value: High.**

## Implementation effort
**Medium**, mostly inside `oe_notifications`, plus small event-publish calls in other modules.
1. **`NotificationPreference` model**: `user_id`, `event_type` (or a wildcard), channels `{in_app, email, push, digest}`, `digest_frequency`, `quiet_hours`, `timezone`. Add GET/PUT `/api/v1/notifications/preferences` and a Settings tab.
2. **Channel dispatcher in `service.notify_users()`**:
   - Resolve each recipient's preferences and write the in-app row.
   - Email urgent events through `core/email`, flag digest rows `digest_pending`, and send web push.
   - Render the i18n title and body keys in the user's locale.
3. **Digest job**: a periodic task (Celery beat when Redis is present, an in-process scheduler otherwise). It groups pending rows per user and project, renders one HTML email, then marks the rows sent.
4. **Web push**:
   - Add a `PushSubscription` table.
   - Generate VAPID keys at first start.
   - Add a `push` event handler to the frontend service worker.
   - Send with `pywebpush`.
   - Remove expired subscriptions when sending returns 404 or 410.
   - On iOS, push only works for PWAs saved to the Home Screen (iOS 16.4+).
5. **Wider coverage**: add subscribers for the RFI, submittals, change orders, tendering, punch list, schedule and validation events. Ship due-date reminders as a scheduled scan.
6. **Optional**: replace 30 s polling with SSE, and add a "forward to chat" channel through the existing integrations (Slack, Teams, Telegram).

## Building blocks
- **pywebpush** plus **py_vapid** for Web Push encryption and VAPID (MPL-2.0, free): https://github.com/web-push-libs/pywebpush
- **Standard Web Push / Service Worker / Notifications APIs** (free). iOS supports them for Home Screen web apps since 16.4: https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
- **Apprise**: one Python API for 100+ services (email, ntfy, Telegram, Matrix and others), a cheap way to add an "external channel" option (BSD-2-Clause per its repo): https://github.com/caronc/apprise
- **ntfy**: a self-hostable HTTP-to-phone push server, an alternative for teams that do not want to install a PWA (Apache-2.0 / GPLv2): https://github.com/binwiederhier/ntfy
- **Novu**: full notification infrastructure with digests, a preference center and an inbox component. Its core is open-source with commercially licensed enterprise parts (verify the LICENSE before adopting). Its **official MCP server** (https://docs.novu.co/platform/build-with-ai/mcp) targets Novu Cloud only, not self-hosted installs. It is too heavy as a core dependency, so treat it at most as an optional connector module.
- I found no construction-specific notification MCP server; none appears to exist.

## Priority: 4/5 — the in-app foundation and SMTP already exist, so a Medium effort for preferences, email routing, digests, web push and more event coverage turns a passive bell into the system that stops a small firm missing deadlines.

## Sources
- https://github.com/web-push-libs/pywebpush
- https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
- https://webkit.org/blog/13966/webkit-features-in-safari-16-4/
- https://github.com/caronc/apprise
- https://github.com/binwiederhier/ntfy
- https://docs.novu.co/platform/what-is-novu
- https://docs.novu.co/platform/build-with-ai/mcp
