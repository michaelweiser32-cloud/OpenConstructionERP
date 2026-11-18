# 050. Calendar connectors (Google Calendar, Outlook/Graph, CalDAV, iCal feeds)

## What it does
Puts meetings, inspections, schedule milestones and task due dates from the ERP into the calendars people already use: Google Calendar, Outlook / Microsoft 365, Apple and CalDAV servers such as Nextcloud. The simplest version is a read-only subscription feed (ICS) that works everywhere. A two-way connector also creates real invites for attendees and site contacts, updates them when a date slips, and can read free/busy times so meetings land in a free slot. It could also bring accepted or declined replies back into `meetings`.

## Already in the codebase (with file paths)
- `backend/app/modules/integrations/router.py`: `GET /calendar/{project_id}.ics` builds an RFC 5545 feed by hand. It includes meetings, tasks (as VTODO), quality inspections and schedule milestones, and it says it works with Google, Outlook and Apple.
- `backend/app/modules/integrations/__init__.py` lists "calendar feeds" as part of the integrations module. `frontend/src/features/integrations/IntegrationsPage.tsx` shows the feed link in the UI.
- Problems found in the current feed:
  - **Security:** the API key is checked only against its first 8 characters (`key_prefix`), not the full hash. Nothing checks that the key owner can access `project_id`.
  - **RFC 5545:** every event is missing the required `DTSTAMP` property, long lines are not folded, and date-only values become 09:00Z instead of all-day `VALUE=DATE` entries. There is also no `DTEND`/`DURATION`, `LOCATION` or `URL` back to the record, no timezone handling, and `_ical_escape` misses `\r`.
  - Everything sits in a single router function with no service, tests or validation rules.
- There is no Google, Graph or CalDAV client, no OAuth token storage for calendars, and no `.ics` invite attached to meeting emails (`integrations/email_service.py`).

## Who it helps and how much
Small estimating and construction firms run on phone calendars. Site inspections, client meetings, tender deadlines (from `tendering`/`rfq_bidding`) and milestones are missed when they live only in the ERP. A correct ICS feed alone covers about 80% of the value at almost no cost. Two-way Google/Outlook sync mainly helps project managers who send invites to subcontractors and inspectors. Value is high for adoption and medium for depth.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
- **Small (fix and extend the feed):** move the feed into `integrations/calendar/service.py` and generate it with the `icalendar` library. Fix the auth: full-hash API key check, project permission check, and a per-feed revocable token. Add all-day events, `DTSTAMP`/`DTEND`, tender deadlines and RFI/submittal due dates, a per-user "all my projects" feed, and a `METHOD:REQUEST` `.ics` attachment on meeting invite emails. Add a `calendar_feed_validity` rule that checks required properties and date order.
- **Medium (two-way connectors):** add a new plugin module `oe_calendar_sync` with `depends=["oe_integrations","oe_meetings","oe_schedule"]`. It has a provider interface with Google, Graph and CalDAV adapters, encrypted OAuth tokens in its own model, and an event-bus subscriber on `meeting.created/updated` and `activity.updated` that pushes changes. Incoming changes come through Google push channels or Graph change notifications. An incoming date change is shown as a proposed change for a person to confirm, never applied automatically.
- **erp_chat:** add `tools.py` entries `list_upcoming_events` and `propose_meeting_slot` (free/busy lookup).

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- `icalendar` (Python): generates and parses ICS files, BSD license. https://icalendar.readthedocs.io/en/stable/
- `caldav` (Python): RFC 4791 CalDAV client for Nextcloud, iCloud and Radicale servers. Dual-licensed Apache-2.0 / GPL-3.0. https://github.com/python-caldav/caldav
- Google Calendar API: events, free/busy and push channels. Standard use is free, with per-project and per-user per-minute quotas. Google's usage-limits page mentions planned charges for traffic over quota, so check current terms. https://developers.google.com/calendar/pricing
- Microsoft Graph events API (`POST /me/events`, delegated `Calendars.ReadWrite`, or `Calendars.ReadWrite.Shared` for shared calendars). Included with Microsoft 365. https://learn.microsoft.com/en-us/graph/api/user-post-events
- MCP: Google has no official Calendar MCP server. The most established community server is `nspady/google-calendar-mcp` (MIT). https://github.com/nspady/google-calendar-mcp
- MCP: `Softeria/ms-365-mcp-server` (MIT, community) covers Microsoft 365 mail and calendar through Graph. https://github.com/Softeria/ms-365-mcp-server
- Neither MCP server replaces a server-side connector. Both are useful only for an AI assistant working beside the ERP.

## Priority: 4/5 — Fixing and extending the existing ICS feed is cheap and benefits every user (the auth fix is urgent); two-way Google/Outlook sync is a sensible second step.

## Sources
- https://datatracker.ietf.org/doc/html/rfc5545
- https://icalendar.readthedocs.io/en/stable/
- https://pypi.org/project/caldav
- https://github.com/python-caldav/caldav
- https://developers.google.com/calendar/pricing
- https://developers.google.com/calendar/quota
- https://learn.microsoft.com/en-us/graph/api/user-post-events
- https://learn.microsoft.com/en-au/graph/outlook-create-event-in-shared-delegated-calendar
- https://github.com/nspady/google-calendar-mcp
- https://github.com/Softeria/ms-365-mcp-server
