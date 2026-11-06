"""
Gmail client using SMTP (send) and Gmail API with app password auth.
Simpler than OAuth for demo mode — uses a Gmail app password.
"""

import os
import base64
import logging
import imaplib
import email
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class GmailClient:
    def __init__(self):
        self.assistant_email = os.environ["ASSISTANT_EMAIL"]
        self.app_password = os.environ["GMAIL_APP_PASSWORD"]
        self._calendar = None
        self._build_calendar()

    def _build_calendar(self):
        """Build Google Calendar service using API key or skip if not configured."""
        try:
            from google.oauth2 import service_account
            import json
            sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
            if sa_json:
                sa_info = json.loads(sa_json)
                creds = service_account.Credentials.from_service_account_info(
                    sa_info,
                    scopes=["https://www.googleapis.com/auth/calendar"],
                ).with_subject(self.assistant_email)
                self._calendar = build("calendar", "v3", credentials=creds)
        except Exception as e:
            logger.warning(f"Calendar not configured: {e}")

    # ── Send email via SMTP ────────────────────────────────────────────────────

    def send_reply(self, thread_id: str, to: str, subject: str, html_body: str):
        """Send an HTML reply via Gmail SMTP."""
        msg = MIMEMultipart("alternative")
        msg["To"] = to
        msg["From"] = self.assistant_email
        msg["Subject"] = f"Re: {subject}" if not subject.lower().startswith("re:") else subject

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(self.assistant_email, self.app_password)
            server.sendmail(self.assistant_email, [to], msg.as_string())

        logger.info(f"Reply sent to {to}")

    # ── Fetch email via IMAP ───────────────────────────────────────────────────

    def get_latest_emails(self, limit: int = 10) -> list:
        """Fetch the latest unread emails from inbox via IMAP."""
        messages = []
        with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
            imap.login(self.assistant_email, self.app_password)
            imap.select("INBOX")

            _, data = imap.search(None, "UNSEEN")
            ids = data[0].split()[-limit:]  # most recent N

            for msg_id in reversed(ids):
                _, msg_data = imap.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                messages.append({"id": msg_id.decode(), "raw": msg})

        return messages

    def mark_as_read(self, msg_id: str):
        """Mark a message as read via IMAP."""
        with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
            imap.login(self.assistant_email, self.app_password)
            imap.select("INBOX")
            imap.store(msg_id, "+FLAGS", "\\Seen")

    # ── Google Calendar ────────────────────────────────────────────────────────

    def find_free_slots(self, emails: list, start: str, end: str) -> dict:
        """Check free/busy. Returns empty if calendar not configured."""
        if not self._calendar:
            logger.warning("Calendar not configured — returning empty busy list")
            return {"calendars": {}}

        return self._calendar.freebusy().query(body={
            "timeMin": start,
            "timeMax": end,
            "items": [{"id": e} for e in emails],
        }).execute()

    def create_event(self, organizer_email: str, event: dict) -> dict:
        """Create a Google Calendar event."""
        if not self._calendar:
            logger.warning("Calendar not configured — skipping event creation")
            return {"id": "no-calendar"}

        return self._calendar.events().insert(
            calendarId=organizer_email,
            body=event,
            sendUpdates="all",
            conferenceDataVersion=1,
        ).execute()
