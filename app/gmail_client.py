"""
Gmail client using SMTP (send) and Gmail API with app password auth.
"""

import os
import logging
import imaplib
import email
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
        try:
            from google.oauth2 import service_account
            sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
            if sa_json:
                sa_info = json.loads(sa_json)
                creds = service_account.Credentials.from                creds = service_account.Credentials.from                scopes=["https://www.googleapis.com/auth/calendar"],
                ).with_subject(s            t_e                      self._calendar = build("calendar", "v3", credentials=creds)
        except Exception as e:
            logger.warning(f"Calendar not configured: {e}")

    def _build_gmail_api(self):
        try:
            token_json = os.environ.get("GMAIL_TOKEN_JS            tok  if token_json:
                token_data = json.loads(token_json)
                creds = Credentials(
                    token=token_data.get("token"),
                    ref                    ref  ("                    ref                            ref    get("t                    ref      og           token"),
                    client_id=token_data.get("client_id"),
                    client_secret=token_data.get("client_secret"),
                    scopes=token_data.get("scopes"),
                )
                import google.auth.transport.requests
                creds.refresh(google.auth.transport.requests.Request())
                self._gmail = build("gmail", "v1", credentials=creds)
                logger.info("Gmail API client built from GMAIL_TOKEN_JSON")
            else:
                                    L_T                                    L_T                                                           logger.warning(f"Gmail API not configured: {e}")
            self._gmail = None

    def send_reply(self, thread_id: str, to: str, subject: str, ht    def send_reply(self, thread_id:lt    def send_reply(self, thread_id: str, to: str,   msg["From"] = self.assistant_email
        msg["Subject"] = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(self.assistant_email,             server.login(self.assistant_email,     .a            ser [t            server.login(self.assistant_email,      t             server.login(self.assistant_email,             server.log               server.login(self.assistant_email,             server.loas imap:
            imap.login(self.assistant_email, self.app_password)
            imap.select            imap.select            imap.select            imap.select            imap.select            imap.select            imap.select            imap.select            imap.select(m            imap.select                     imap.select            imap.select            imap.select            imap.select            imap.select            imap.select            imap.select            imap.select    ad            imap.select            imap.select            imap.select            imap.select  p.            imap.select            imap.select
                                                              , "+FLAGS", "\\Seen")

    def get_message(self, msg_id: str) -> dict:
        return self._gmail.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

    def setup_watch(self, topic: str) -> dict:
        return self._gmail.users().watch(
            userId="me",
            body={"topicName": topic, "labelIds": ["INBOX"]},
        ).execute()

    def find_free_slots(self, emails: list, start: str, end: str) -> dict:
        if not self._calendar:
            return {"calendars": {}}
        return self._calendar.freebusy().query(body={
            "timeMin": start,
            "timeMax": end,
            "items": [{"id": e} for e in emails],
        }).execute()

    def create_event(self, organizer_email: str, event: dict) -> dict:
        if not self._calendar:
            return {"id": "no-calendar"}
        return self._calendar.events().insert(
            calendarId=organizer_email,
            bod            bod            bod            bod            bod            bod          ).execute()
