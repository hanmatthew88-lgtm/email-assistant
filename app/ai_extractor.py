"""
Claude API integration — extracts scheduling intent and details from emails.
Replaces the naive keyword matching in main.py with accurate NLU.
"""

import os
import json
import logging
from datetime import datetime, timezone

import anthropic

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


SYSTEM_PROMPT = """You are a scheduling assistant that reads emails and extracts meeting details.
Extract information as JSON. Be precise. If something is not mentioned, use null.
Today's date is provided in each request."""


EXTRACTION_PROMPT = """Extract scheduling details from this email.

Today's date: {today}

Email subject: {subject}
Email body: {body}

Return a JSON object with these fields:
{{
  "intent": "schedule" | "reschedule" | "cancel" | "none",
  "duration_minutes": number or null,
  "preferred_dates": ["YYYY-MM-DD"] or [],
  "preferred_times": ["HH:MM"] or [],
  "timezone": "America/New_York" or null,
  "meeting_title": "string or null",
  "urgency": "asap" | "this_week" | "next_week" | "flexible",
  "notes": "any other relevant context or null"
}}

Examples:
- "Can we jump on a quick 15 min call tomorrow?" → duration_minutes: 15, urgency: asap
- "Let's find time next week for a 1 hour strategy session" → duration_minutes: 60, urgency: next_week
- "Anytime Thursday or Friday works for me" → preferred_dates based on those days
- "Morning works best, around 9 or 10am EST" → preferred_times: ["09:00", "10:00"], timezone: "America/New_York"

Return only valid JSON, no explanation."""


async def extract_scheduling_intent(parsed_email: dict) -> dict:
    """
    Use Claude to extract structured scheduling information from a parsed email.

    Returns a dict with intent, duration, preferred times, etc.
    Falls back to defaults if extraction fails.
    """
    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

    prompt = EXTRACTION_PROMPT.format(
        today=today,
        subject=parsed_email.get("subject", ""),
        body=parsed_email.get("body", "")[:2000],  # cap at 2000 chars to save tokens
    )

    try:
        message = client.messages.create(
            model="claude-haiku-4-5",  # fast + cheap for extraction tasks
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if Claude wraps it
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        extracted = json.loads(raw)
        logger.info(f"Extracted intent: {extracted.get('intent')} | duration: {extracted.get('duration_minutes')}min")
        return extracted

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        return _default_extraction()
    except Exception as e:
        logger.error(f"Claude extraction failed: {e}", exc_info=True)
        return _default_extraction()


async def draft_confirmation_email(
    meeting_title: str,
    start_time: str,
    end_time: str,
    attendees: list[str],
    timezone: str,
    original_email: dict,
) -> str:
    """
    Use Claude to write a natural, friendly confirmation reply.
    """
    prompt = f"""Write a short, friendly email reply confirming a meeting was scheduled.

Meeting: {meeting_title}
Start: {start_time} ({timezone})
End: {end_time}
Attendees: {", ".join(attendees)}

The reply should:
- Be 2-3 sentences max
- Sound natural, not robotic
- Mention the meeting name and time
- Say calendar invites have been sent
- Sign off as "Scheduling Assistant"

Return only the HTML body of the email (use <p> tags)."""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.error(f"Failed to draft confirmation email: {e}")
        # Fallback to template
        return (
            f"<p>Hi,</p>"
            f"<p>I've scheduled <strong>{meeting_title}</strong> for <strong>{start_time} ({timezone})</strong>. "
            f"Calendar invites have been sent to all attendees.</p>"
            f"<p>Thanks,<br>Scheduling Assistant</p>"
        )


async def suggest_meeting_title(email_subject: str, email_body: str) -> str:
    """
    Infer a clean meeting title from the email context.
    """
    prompt = f"""Given this email, suggest a short, professional meeting title (5 words max).

Subject: {email_subject}
Body excerpt: {email_body[:500]}

Return only the meeting title, nothing else."""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=32,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip().strip('"')
    except Exception:
        return email_subject or "Meeting"


def _default_extraction() -> dict:
    """Safe fallback if Claude extraction fails."""
    return {
        "intent": "schedule",
        "duration_minutes": 30,
        "preferred_dates": [],
        "preferred_times": [],
        "timezone": None,
        "meeting_title": None,
        "urgency": "flexible",
        "notes": None,
    }
