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
        try:
            from google.oauth2 import service_account
            import json
                                                   E_ACCOUNT_JSON")
            if sa_json:
                sa_info = json.loads(sa_json)
                creds = service_account.Credentials.from_service_account_info(
                    sa_info,
                          =[   tps://www.g             /a            "],                          bj                          =[   tps:                            =[   tps://www.g  , credentials=creds)
        except Exception as e:
            logger.warning(f"Calendar not configured: {e}")

    def _build_gmail_api(self):
        try:
            import json
            token_json = os.environ.get("GMAIL_TOKEN_JSON")
            if token_json:
                from google.oauth2.credentials import Credentials
                token_data = json.loads(token_json)
                creds = Credentials(
                    token=token_data.get("token"),
                    refresh_token=token_data.get("refresh_token"),
                    token_uri=token_data.get("token_uri                    token_uri=token_data.get("token_uri           ent_id=token_data.get("cli                    token_uri=token_data.et=to                    token_uri=token_data.get("token_uri                    topes"),
                )
                # Refresh token using requests (avoids httplib2 SSL bug on Python 3.14)
                import google.auth.transport.requests
                creds.refresh(google.auth.transport.requests.Reque                creds.refreshmail = build("gmail", "v1", credentials=creds)
                logger.info("Gmail API client built from GMAIL_TOKEN_JSON")
                                                                   not set — Gmail API features (watch, history) unavailable")
                self._gmail = None
        except Exception as e:
            logger.warning(f"Gmail API not configured: {e}")
            self._gmail = None

    def send_r    def send_r    def send_r    def send_r    def send_r    def s:
        msg = MIMEMultipart("alternative")
        msg["To"] = to
        msg["From"] = self.assistant_email
        msg["Subject"] = f"Re: {subject}" if not subject.lower().startswith("re:") else subject
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(self.assistant_email, self.app_password)
            server.login(self.assistant_email, self.o]            server.login(self.assistant_email, self.o]            server.login(self.assistant_email, self.o]            server.login(self.as[]
        with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
            imap.            imap.            imap.            imap.            imap.            imap.            imap.            imap.        ")            imap.            imap)[-limit:]
            for msg_id            for msg_id            for msg_id        p.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                                              de                                                                ad(self, msg_id: str):
        with imaplib.IMAP4_SSL("imap.gmail.com") as imap:
            imap.            imap.            imap.            
            imap.select("INBOX")
            imap.store(msg_id, "+FLAGS", "\\Seen")

    def get_message(self, msg_id: str) -> dict    def get_message(self, msg_id: str) -> dict    def get_message(self, msg_id: str) -> dict    def get_message(self, msg_id: str) -> dict    def get_message(self, msg_id: str) -> dict    def getil.users().watch(
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
        })        })        })        })        })        })        })        }ict) -> dict:
        if not self._calendar:
            return {"id": "no-calendar"}
        return self._calendar.events().insert(
            calendarId=organizer_email,
            body=event,
            sendUpdates="all",
            conferenceDataVersion=1,
        ).execute()
