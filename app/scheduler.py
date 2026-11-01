"""
Scheduling handler — interprets a parsed email and creates / reschedules
calendar events via Microsoft Graph, using Claude for intent extraction.
"""

import logging
import re
from datetime import datetime, timezone, timedelta

from app.graph_client import GraphClient
from app.ai_extractor import extract_scheduling_intent, draft_confirmation_email, suggest_meeting_title

logger = logging.getLogger(__name__)


async def handle_scheduling_request(graph: GraphClient, parsed: dict, reschedule: bool = False):
    """
    Given a parsed email:
    1. Use Claude to extract intent, duration, preferred times
    2. Find a free slot using Graph findMeetingTimes
    3. Create the calendar event with Teams link
    4. Reply with a Claude-drafted confirmation
    """
    # Step 1: Extract details with Claude
    extracted = await extract_scheduling_intent(parsed)

    if extracted["intent"] == "none":
        logger.info("No scheduling intent detected — skipping")
        return

    duration = extracted.get("duration_minutes") or 30
    urgency = extracted.get("urgency", "flexible")
    preferred_tz = extracted.get("timezone") or "UTC"

    # Step 2: Build search window based on urgency
    now = datetime.now(timezone.utc)
    if urgency == "asap":
        search_start = now + timedelta(hours=1)
        search_end = now + timedelta(days=2)
    elif urgency == "this_week":
        search_start = now + timedelta(hours=1)
        search_end = now + timedelta(days=5)
    elif urgency == "next_week":
        days_until_monday = (7 - now.weekday()) % 7 or 7
        search_start = (now + timedelta(days=days_until_monday)).replace(hour=9, minute=0, second=0)
        search_end = search_start + timedelta(days=5)
    else:  # flexible
        search_start = now + timedelta(hours=1)
        search_end = now + timedelta(days=14)

    # Cap to business hours
    search_start = search_start.replace(hour=max(search_start.hour, 9))
    search_end = search_end.replace(hour=17, minute=0, second=0, microsecond=0)

    # Step 3: Get attendees
    attendees = _extract_attendees(parsed, graph.assistant_email)
    if not attendees:
        logger.warning("No attendees found — cannot schedule")
        return

    logger.info(f"Finding {duration}min slot for {attendees} | urgency: {urgency}")

    # Step 4: Find free slot
    slots = await graph.find_free_slots(
        emails=attendees,
        start=search_start.strftime("%Y-%m-%dT%H:%M:%S"),
        end=search_end.strftime("%Y-%m-%dT%H:%M:%S"),
        duration_minutes=duration,
    )

    suggestions = slots.get("meetingTimeSuggestions", [])

    if not suggestions:
        logger.warning("No free slots found")
        await graph.send_reply(
            parsed["id"],
            "<p>Hi,</p><p>I wasn't able to find a time that works for everyone. "
            "Could you suggest a few times that work for you?</p><p>Thanks,<br>Scheduling Assistant</p>",
        )
        return

    best = suggestions[0]["meetingTimeSlot"]
    start_dt = best["start"]["dateTime"]
    end_dt = best["end"]["dateTime"]
    slot_tz = best["start"]["timeZone"]

    # Step 5: Get meeting title
    meeting_title = extracted.get("meeting_title") or await suggest_meeting_title(
        parsed["subject"], parsed["body"]
    )
    if reschedule:
        meeting_title = f"[Rescheduled] {meeting_title}"

    # Step 6: Create calendar event
    event = _build_event(meeting_title, start_dt, end_dt, slot_tz, attendees)
    created = await graph.create_event(parsed["from"], event)
    logger.info(f"Event created: {created.get('id')} — {meeting_title} @ {start_dt}")

    # Step 7: Claude-drafted confirmation reply
    formatted_start = _format_time(start_dt, preferred_tz)
    formatted_end = _format_time(end_dt, preferred_tz)

    reply_html = await draft_confirmation_email(
        meeting_title=meeting_title,
        start_time=formatted_start,
        end_time=formatted_end,
        attendees=attendees,
        timezone=preferred_tz,
        original_email=parsed,
    )
    await graph.send_reply(parsed["id"], reply_html)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_attendees(parsed: dict, assistant_email: str) -> list[str]:
    all_emails = set()
    all_emails.add(parsed["from"])
    all_emails.update(parsed["to"])
    all_emails.update(parsed["cc"])
    all_emails.discard(assistant_email.lower())
    return list(all_emails)


def _build_event(title: str, start: str, end: str, tz: str, attendees: list[str]) -> dict:
    return {
        "subject": title,
        "body": {"contentType": "Text", "content": "Meeting scheduled by AI Scheduling Assistant."},
        "start": {"dateTime": start, "timeZone": tz},
        "end":   {"dateTime": end,   "timeZone": tz},
        "attendees": [
            {"emailAddress": {"address": e}, "type": "required"} for e in attendees
        ],
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
    }


def _format_time(iso: str, tz: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%A, %B %-d at %-I:%M %p") + f" ({tz})"
    except Exception:
        return iso
