"""
Gmail-specific scheduling handler.
Same logic as scheduler.py but uses GmailClient + Google Calendar
instead of Microsoft Graph.
"""

import logging
from datetime import datetime, timezone, timedelta

from app.gmail_client import GmailClient
from app.ai_extractor import extract_scheduling_intent, draft_confirmation_email, suggest_meeting_title

logger = logging.getLogger(__name__)


async def handle_gmail_scheduling(client: GmailClient, parsed: dict, reschedule: bool = False):
    """
    1. Claude extracts intent and details
    2. Check free/busy via Google Calendar
    3. Create event with Google Meet link
    4. Reply to thread with Claude-drafted confirmation
    """
    import asyncio

    # Step 1: Claude extraction (run sync in thread since gmail client is sync)
    extracted = await extract_scheduling_intent(parsed)

    if extracted["intent"] == "none":
        logger.info("No scheduling intent — skipping")
        return

    duration = extracted.get("duration_minutes") or 30
    urgency = extracted.get("urgency", "flexible")

    # Step 2: Build search window
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
    else:
        search_start = now + timedelta(hours=1)
        search_end = now + timedelta(days=14)

    # Step 3: Get attendees
    attendees = _extract_attendees(parsed, client.assistant_email)
    if not attendees:
        logger.warning("No attendees — cannot schedule")
        return

    # Step 4: Find a free slot
    slot = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: _find_free_slot(client, attendees, search_start, search_end, duration)
    )

    if not slot:
        client.send_reply(
            parsed["thread_id"], parsed["from"], parsed["subject"],
            "<p>Hi,</p><p>I wasn't able to find a time that works for everyone. "
            "Could you suggest a few times?</p><p>Thanks,<br>Scheduling Assistant</p>"
        )
        return

    start_dt, end_dt = slot

    # Step 5: Meeting title
    meeting_title = extracted.get("meeting_title") or await suggest_meeting_title(
        parsed["subject"], parsed["body"]
    )
    if reschedule:
        meeting_title = f"[Rescheduled] {meeting_title}"

    # Step 6: Create Google Calendar event
    event = _build_google_event(meeting_title, start_dt, end_dt, attendees)
    loop = asyncio.get_event_loop()
    created = await loop.run_in_executor(
        None, lambda: client.create_event(parsed["from"], event)
    )
    logger.info(f"Event created: {created.get('id')} — {meeting_title}")

    # Step 7: Claude confirmation reply
    tz = extracted.get("timezone") or "UTC"
    formatted_start = start_dt.strftime("%A, %B %-d at %-I:%M %p") + f" ({tz})"
    formatted_end = end_dt.strftime("%-I:%M %p")

    reply_html = await draft_confirmation_email(
        meeting_title=meeting_title,
        start_time=formatted_start,
        end_time=formatted_end,
        attendees=attendees,
        timezone=tz,
        original_email=parsed,
    )

    await loop.run_in_executor(
        None,
        lambda: client.send_reply(parsed["thread_id"], parsed["from"], parsed["subject"], reply_html)
    )


def _extract_attendees(parsed: dict, assistant_email: str) -> list:
    emails = set()
    emails.add(parsed["from"])
    emails.update(parsed["to"])
    emails.update(parsed["cc"])
    emails.discard(assistant_email.lower())
    return list(emails)


def _find_free_slot(client: GmailClient, attendees: list, search_start: datetime,
                    search_end: datetime, duration_minutes: int):
    """
    Walk through business hours in the search window and find the first
    slot where all attendees are free.
    """
    busy = client.find_free_slots(
        emails=attendees,
        start=search_start.isoformat(),
        end=search_end.isoformat(),
    )

    # Collect all busy intervals
    busy_intervals = []
    for calendar_data in busy.get("calendars", {}).values():
        for period in calendar_data.get("busy", []):
            busy_intervals.append((
                datetime.fromisoformat(period["start"].replace("Z", "+00:00")),
                datetime.fromisoformat(period["end"].replace("Z", "+00:00")),
            ))

    # Walk through business hours (9am-5pm) in 30min increments
    candidate = search_start.replace(minute=0, second=0, microsecond=0)
    if candidate.hour < 9:
        candidate = candidate.replace(hour=9)

    delta = timedelta(minutes=duration_minutes)
    increment = timedelta(minutes=30)

    while candidate < search_end:
        # Skip outside business hours
        if candidate.hour < 9 or candidate.hour >= 17:
            candidate = candidate.replace(hour=9) + timedelta(days=1)
            continue
        # Skip weekends
        if candidate.weekday() >= 5:
            candidate += timedelta(days=1)
            continue

        slot_end = candidate + delta
        if slot_end.hour > 17:
            candidate += increment
            continue

        # Check if slot overlaps any busy period
        overlap = any(
            candidate < b_end and slot_end > b_start
            for b_start, b_end in busy_intervals
        )
        if not overlap:
            return candidate, slot_end

        candidate += increment

    return None


def _build_google_event(title: str, start: datetime, end: datetime, attendees: list) -> dict:
    return {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end":   {"dateTime": end.isoformat(),   "timeZone": "UTC"},
        "attendees": [{"email": e} for e in attendees],
        "conferenceData": {
            "createRequest": {
                "requestId": f"meet-{int(start.timestamp())}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "guestsCanModify": False,
        "sendUpdates": "all",
    }
