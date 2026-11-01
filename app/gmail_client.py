"""
Gmail API client — handles auth and API calls for the assistant mailbox.
Uses OAuth 2.0 service account (domain-wide delegation) OR
user OAuth credentials for a single Gmail account (demo mode).
"""

import os
import base64
import logging
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]


class GmailClient:
    def __init__(self):
        self.assistant_email = os.environ["ASSISTANT_EMAIL"]
        self._gmail = None
        self._calendar = None
        self._build_services()

    def _build_services(self):
        """Build Gmail and Calendar API service clients."""
        creds = self._get_credentials()
        self._gmail = build("gmail", "v1", credentials=creds)
        self._calendar = build("calendar", "v3", credentials=creds)
        logger.info(f"Gmail client initialized for {self.assistant_email}")

    def _get_credentials(self):
        """
        Load credentials from environment.
        In demo mode: uses OAuth token stored as JSON in GMAIL_TOKEN_JSON env var.
        In production: uses service account with domain-wide delegation.
        """
        token_json = os.environ.get("GMAIL_TOKEN_JSON")
        if token_json:
            # Demo mode — OAuth credentials
            creds_data = json.loads(token_json)
            creds = Credentials(
                token=creds_data.get("token"),
                refresh_token=creds_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.environ["GOOGLE_CLIENT_ID"],
                client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
                scopes=SCOPES,
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return creds

        # Production mode — service account
        sa_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
        sa_info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=SCOPES
        )
        return creds.with_subject(self.assistant_email)

    # ── Messages ───────────────────────────────────────────────────────────────

    def get_message(self, message_id: str) -> dict:
        """Fetch a full Gmail message."""
        return self._gmail.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()

    def send_reply(self, thread_id: str, to: str, subject: str, html_body: str):
        """Send an HTML reply in the same thread."""
        msg = MIMEMultipart("alternative")
        msg["To"] = to
        msg["From"] = self.assistant_email
        msg["Subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject
        msg.attach(MIMEText(html_body, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self._gmail.users().messages().send(
            userId="me",
            body={"raw": raw, "threadId": thread_id},
        ).execute()
        logger.info(f"Reply sent to {to}")

    # ── Calendar ───────────────────────────────────────────────────────────────

    def create_event(self, organizer_email: str, event: dict) -> dict:
        """Create a Google Calendar event with invites."""
        return self._calendar.events().insert(
            calendarId=organizer_email,
            body=event,
            sendUpdates="all",  # sends invite emails to attendees
        ).execute()

    def find_free_slots(self, emails: list, start: str, end: str) -> dict:
        """Check free/busy for a list of emails."""
        return self._calendar.freebusy().query(body={
            "timeMin": start,
            "timeMax": end,
            "items": [{"id": e} for e in emails],
        }).execute()

    # ── Watch (webhook setup) ──────────────────────────────────────────────────

    def setup_watch(self, topic_name: str) -> dict:
        """
        Tell Gmail to push notifications to a Google Pub/Sub topic
        when new messages arrive in the inbox.
        topic_name format: projects/{project_id}/topics/{topic_name}
        """
        return self._gmail.users().watch(
            userId="me",
            body={
                "topicName": topic_name,
                "labelIds": ["INBOX"],
                "labelFilterBehavior": "INCLUDE",
            },
        ).execute()
