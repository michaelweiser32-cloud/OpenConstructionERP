# 057. Meeting minutes and action items (agenda templates, carry-forward items, AI summaries)

## What it does
Site meetings, OAC (owner-architect-contractor) meetings, pre-bid and subcontractor coordination meetings drive most decisions on a small job. This feature covers: reusable agenda templates per meeting type, recurring "meeting series" where open items carry forward automatically into the next agenda, minutes captured per agenda item, action items with owner and due date, distribution of minutes (PDF/email plus calendar invite for the next meeting), and AI that turns a transcript or recording into draft minutes for human review. Procore's Meetings tool is the reference: it converts agenda to minutes, offers a "Follow Up Meeting" action and carries outstanding items to the next meeting.

## Already in the codebase (with file paths)
Coverage is already substantial; the gap is mainly series/templates and connectors.
- `backend/app/modules/meetings/models.py`: `Meeting` with `meeting_type`, `attendees`, `agenda_items`, `action_items` (JSON lists), `minutes`, `status`, `document_ids`.
- `backend/app/modules/meetings/router.py`: CRUD, `/stats/`, `/open-actions/` (cross-meeting open items), `/{id}/complete/`, `/{id}/export/pdf/`, and `/import-summary/`, which parses .txt/.vtt/.srt/.docx/.pdf transcripts with heuristics and, if AI keys are set, an LLM, with a `preview` mode for human review.
- `backend/app/modules/meetings/service.py`: `complete_meeting` creates Task rows from action items and publishes `meeting.action_items_created` on the event bus.
- `backend/app/modules/integrations/email_service.py`: has `template_meeting_invitation`.
- `frontend/src/features/meetings/MeetingsPage.tsx`, `api.ts`.
- **Missing:** agenda templates, a series/parent link (`previous_meeting_id`), automatic carry-forward of open action items and unresolved agenda items, item IDs that stay stable across meetings (for example "3.02"), distribution with acknowledgement, .ics export, direct pull of transcripts from Teams/Zoom, audio transcription, and erp_chat tools for meetings.

## Who it helps and how much
- **Project managers and site supervisors at small general contractors:** they save about 30-60 minutes per weekly meeting by not retyping minutes, and fewer items get lost.
- **Estimators in pre-bid and scope-review meetings:** the meeting record links decisions to BOQ, RFI and change orders.
- **Owners and subcontractors:** they get consistent, timely minutes. A clear record of who was assigned what reduces disputes.
Value is high because meetings happen every week on every project. The AI value is real but secondary: carry-forward and templates help on every meeting, transcripts only when someone recorded.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Medium overall** (series, templates and .ics are Small; the connectors are Medium).
1. In `meetings`, add a `MeetingTemplate` model (type, default agenda sections, default attendees) and `series_id` / `previous_meeting_id` on `Meeting`. Add `POST /{id}/follow-up/`, which clones attendees and template sections and copies open action items and unresolved agenda items with their stable item numbers. It writes a `carried_from` reference into each copied item. This needs an Alembic migration.
2. Add `GET /{id}/ics/` using `icalendar`, and attach the file to the existing invitation email.
3. Add validation rules (per CLAUDE.md, every module needs them). Examples: an action item with no owner or due date, an item overdue but still open, minutes not distributed within N days.
4. Add connector plugins (zip modules) for Microsoft Graph `callTranscript` content (VTT) and Zoom cloud-recording `CC`/`TRANSCRIPT` files. They feed the existing `/import-summary/` preview, so AI output is still confirmed by a human before it is saved.
5. Optionally, local transcription of audio files with faster-whisper as a Celery task.
6. Add `erp_chat/tools.py` tools: list open actions, draft agenda for the next meeting.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **icalendar (Python):** RFC 5545 generator. BSD-2-Clause. https://pypi.org/project/icalendar/
- **faster-whisper:** local speech-to-text on CTranslate2. MIT (Whisper weights are MIT too). https://github.com/SYSTRAN/faster-whisper
- **WhisperX:** adds word timestamps and speaker diarization. Sources disagree on its license (BSD vs MIT), and the pyannote diarization models need a separate license acceptance. Verify both before bundling. https://github.com/m-bain/whisperX
- **Microsoft Graph callTranscript API:** returns Teams transcripts as `text/vtt`. Needs an M365 tenant and permissions; transcript content access is metered. https://learn.microsoft.com/en-us/graph/api/calltranscript-get
- **Zoom Cloud Recording API:** VTT transcript files, plus a "recording transcript completed" webhook. Needs paid Zoom cloud recording and user OAuth. https://developers.zoom.us/docs/build/cloud-recording/
- **Fireflies.ai MCP server:** an official hosted MCP server for transcripts, summaries and action items. Commercial SaaS. https://docs.fireflies.ai/mcp-tools/overview
- **No official Procore, Teams or Zoom MCP server for meeting minutes was verified** during this research.

## Priority: 4/5 — frequent weekly workflow and most plumbing exists; carry-forward plus templates is a cheap, high-value gap
## Sources
- https://v2.support.procore.com/en-ca/product-manuals/meetings-project/
- https://en-au.support.procore.com/tc/Fletcher_Residential/Industrial/Industrial_-_Contractor/Meetings
- https://learn.microsoft.com/en-us/graph/api/calltranscript-get
- https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/meeting-transcripts/api-transcripts
- https://developers.zoom.us/docs/build/cloud-recording/
- https://devforum.zoom.us/t/download-zoom-transcription-vtt-file-via-zoom-api/108073
- https://pypi.org/project/icalendar/
- https://github.com/SYSTRAN/faster-whisper
- https://github.com/m-bain/whisperX
- https://docs.fireflies.ai/mcp-tools/overview
