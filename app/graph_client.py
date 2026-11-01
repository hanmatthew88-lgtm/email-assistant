"""
Microsoft Graph API client — handles auth token refresh and API calls.
Uses the client credentials flow (app-only) for the assistant mailbox.
"""

import os
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


class GraphClient:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str, assistant_email: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.assistant_email = assistant_email
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    async def _get_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_URL.format(tenant_id=self.tenant_id),
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._token_expiry = time.time() + data["expires_in"]
            return self._token

    async def _get(self, path: str, **kwargs) -> dict:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GRAPH_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict, **kwargs) -> dict:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GRAPH_BASE}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=json,
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()

    async def _patch(self, path: str, json: dict) -> dict:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{GRAPH_BASE}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=json,
            )
            resp.raise_for_status()
            return resp.json()

    # ── Messages ───────────────────────────────────────────────────────────────

    async def get_message(self, message_id: str) -> dict:
        """Fetch a full email message from the assistant mailbox."""
        user = self.assistant_email
        return await self._get(
            f"/users/{user}/messages/{message_id}",
            params={"$select": "id,subject,from,toRecipients,ccRecipients,body,receivedDateTime"},
        )

    async def send_reply(self, message_id: str, html_body: str):
        """Reply to a message from the assistant mailbox."""
        user = self.assistant_email
        await self._post(
            f"/users/{user}/messages/{message_id}/reply",
            json={"message": {"body": {"contentType": "HTML", "content": html_body}}},
        )

    # ── Calendar ───────────────────────────────────────────────────────────────

    async def create_event(self, organizer_email: str, event: dict) -> dict:
        """
        Create a calendar event on behalf of the organizer.
        Requires Calendars.ReadWrite application permission.
        """
        return await self._post(f"/users/{organizer_email}/events", json=event)

    async def find_free_slots(self, emails: list[str], start: str, end: str, duration_minutes: int) -> dict:
        """
        Use Graph findMeetingTimes to get available slots for all attendees.
        """
        return await self._post(
            f"/users/{self.assistant_email}/findMeetingTimes",
            json={
                "attendees": [{"emailAddress": {"address": e}, "type": "required"} for e in emails],
                "timeConstraint": {
                    "activityDomain": "work",
                    "timeSlots": [{"start": {"dateTime": start, "timeZone": "UTC"},
                                   "end": {"dateTime": end, "timeZone": "UTC"}}],
                },
                "meetingDuration": f"PT{duration_minutes}M",
                "returnSuggestionReasons": True,
                "minimumAttendeePercentage": 100,
            },
        )

    # ── Subscriptions ──────────────────────────────────────────────────────────

    async def create_subscription(self, notification_url: str, expiry_datetime: str, client_state: str) -> dict:
        return await self._post(
            "/subscriptions",
            json={
                "changeType": "created",
                "notificationUrl": notification_url,
                "resource": f"/users/{self.assistant_email}/mailFolders/inbox/messages",
                "expirationDateTime": expiry_datetime,
                "clientState": client_state,
            },
        )

    async def renew_subscription(self, subscription_id: str, expiry_datetime: str) -> dict:
        return await self._patch(
            f"/subscriptions/{subscription_id}",
            json={"expirationDateTime": expiry_datetime},
        )
