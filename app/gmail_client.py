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
        self._gmail = None
        self._build_calendar()
        self._build_gmail_api()

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

    def _build_gmail_api(self):
        """Build Gmail API service using OAuth2 credentials."""
        try:
            import json
            token_json = os.environ.get("GMAIL_TOKEN_JSON")
            if token_json:
                from google.oauth2.credentials import Credentials
                token_data = json.loads(token_json)
                creds = Credentials(
                    token=token_data.get("token"),
                    refresh_token=token_data.get("refresh_token"),
                    token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                    client_id=token_data.get("client_id"),
                    client_secret=token_data.get("client_secret"),
                    scopes=token_data.get("scopes"),
                )
                import google.auth.transport.requests
                creds.refresh(google.auth.transport.requests.Request())
                self._gmail = build("gmail", "v1", credentials=creds)
                logger.info("Gmail API client built from GMAIL_TOKEN_JSON")
            else:
                logger.warning("GMAIL_TOKEN_JSON not set — Gmail API features unavailable")
                self._gmail = None
        except Exception as e:
            logger.warning(f"Gmail API not configured: {e}")
            self._gmail = None

    def send_reply(self, thread_id: str, to: str, subject: str, html_body: str):
        """Send an HTML reply via Gmail API (avoids SMTP port blocks on Render)."""
        msg = MIMEMultipart("alternative")
        msg["To"] = to
        msg["From"] = self.assistant_email
        msg["Subject"] = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
        if thread_id:
            msg["References"] = thread_id
            msg["In-Reply-To"] = thread_id
        msg.attach(MIMEText(html_body, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        body = {"raw": raw}
        if thread_id:
            body["threadId"] = thread_id

        self._gmail.users().messages().send(userId="me", body=body).execute()
        logger.info(f"Reply sent to {to}")

    def get_latest_emails(self, limit: int = 10) -> list:
        """Fetch the latest unread emails from inbox via IMAP."""
        messages = []
        with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
            imap.login(self.assistant_email, self.app_password)
            imap.select("INBOX")

            _, data = imap.search(None, "UNSEEN")
            ids = data[0].split()[-limit:]

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

    def get_message(self, msg_id: str) -> dict:
        """Fetch a single Gmail message by ID via Gmail API."""
        return self._gmail.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

    def setup_watch(self, topic: str) -> dict:
        """Register Gmail push notifications to a Pub/Sub topic."""
        return self._gmail.users().watch(
            userId="me",
            body={
                "topicName": topic,
                "labelIds": ["INBOX"],
            }
        ).execute()

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