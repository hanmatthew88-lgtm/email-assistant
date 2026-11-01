"""
Scheduling handler — interprets a parsed email and creates / reschedules
calendar events via Microsoft Graph.
"""

import logging
import re
from datetime import datetime, timezone, timedelta

from app.graph_client import GraphClient

logger = logging.getLogger(__name__)


async def handle_scheduling_request(graph: GraphClient, parsed: dict, reschedule: bool = False):
    """
    Given a parsed email where someone asked to schedule (or reschedule) a meeting:
    1. Extract attendees (sender + CC'd humans, excluding the assistant mailbox)
    2. Find a free slot using Graph findMeetingTimes
    3. Create the calendar event and send invites
    4. Reply to the thread confirming the booking
    """
    attendees = _extract_attendees(parsed, graph.assistant_email)
    if not attendees:
        logger.warning("No attendees found — cannot schedule")
        return

    # Look for a free slot in the next 5 business days
    now = datetime.now(timezone.utc)
    search_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    search_end = (now + timedelta(days=7)).replace(hour=17, minute=0, second=0, microsecond=0)
    duration = _extract_duration(parsed["body"])  # minutes

    logger.info(f"Finding {duration}min slot for: {attendees}")

    slots = await graph.find_free_slots(
        emails=attendees,
        start=search_start.isoformat().replace("+00:00", "Z"),
        end=search_end.isoformat().replace("+00:00", "Z"),
        duration_minutes=duration,
    )

    suggestions = slots.get("meetingTimeSuggestions", [])
    if not suggestions:
        logger.warning("No free slots found")
        await graph.send_reply(
            parsed["id"],
            "<p>Hi,</p><p>I wasn't able to find a time that works for everyone in the next 7 days. "
            "Could you suggest a few times that work for you?</p><p>Thanks,<br>Scheduling Assistant</p>",
        )
        return

    best = suggestions[0]["meetingTimeSlot"]
    start_dt = best["start"]["dateTime"]
    end_dt = best["end"]["dateTime"]
    tz = best["start"]["timeZone"]

    organizer = parsed["from"]
    subject = _clean_subject(parsed["subject"], reschedule)

    event = _build_event(subject, start_dt, end_dt, tz, attendees, parsed["body"])
    created = await graph.create_event(organizer, event)

    logger.info(f"Event created: {created.get('id')} — {subject} @ {start_dt}")

    # Reply to confirm
    formatted_time = _format_time(start_dt, tz)
    reply_html = (
        f"<p>Hi,</p>"
        f"<p>I've scheduled <strong>{subject}</strong> for <strong>{formatted_time}</strong>. "
        f"Calendar invites have been sent to all attendees.</p>"
        f"<p>Thanks,<br>Scheduling Assistant</p>"
    )
    await graph.send_reply(parsed["id"], reply_html)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_attendees(parsed: dict, assistant_email: str) -> list[str]:
    """Collect all humans on the thread, excluding the assistant mailbox."""
    all_emails = set()
    all_emails.add(parsed["from"])
    all_emails.update(parsed["to"])
    all_emails.update(parsed["cc"])
    all_emails.discard(assistant_email.lower())
    return list(all_emails)


def _extract_duration(body: str) -> int:
    """Try to find a meeting duration in the email body. Default 30 min."""
    patterns = [
        (r"(\d+)\s*hour", lambda m: int(m.group(1)) * 60),
        (r"(\d+)\s*hr",   lambda m: int(m.group(1)) * 60),
        (r"(\d+)\s*min",  lambda m: int(m.group(1))),
    ]
    for pattern, extract in patterns:
        m = re.search(pattern, body, re.IGNORECASE)
        if m:
            return extract(m)
    return 30


def _clean_subject(subject: str, reschedule: bool) -> str:
    subject = re.sub(r"^(re|fwd?):\s*", "", subject, flags=re.IGNORECASE).strip()
    return f"[Rescheduled] {subject}" if reschedule else subject


def _build_event(subject: str, start: str, end: str, tz: str, attendees: list[str], body: str) -> dict:
    return {
        "subject": subject,
        "body": {"contentType": "Text", "content": "Meeting scheduled by AI assistant."},
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
