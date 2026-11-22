"""
Gmail webhook router — handles Google Pub/Sub push notifications.
Mount this in main.py alongside the existing Graph routes.
"""

import os
import base64
import json
import logging

from fastapi import APIRouter, Request
from app.gmail_client import GmailClient
from app.gmail_parser import parse_gmail_message
from app.gmail_scheduler import handle_gmail_scheduling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gmail")

_client: GmailClient = None
_last_history_id: str = None


def get_client() -> GmailClient:
    global _client
    if _client is None:
        _client = GmailClient()
    return _client


@router.post("/webhook")
async def gmail_webhook(request: Request):
    global _last_history_id

    body = await request.json()

    pubsub_message = body.get("message", {})
    data_b64 = pubsub_message.get("data", "")
    if not data_b64:
        return {"status": "no data"}

    data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    email_address = data.get("emailAddress")
    history_id = data.get("historyId")

    logger.info(f"Gmail notification for {email_address}, historyId: {history_id}")

    start_id = _last_history_id or str(int(history_id) - 1)
    _last_history_id = history_id

    try:
        client = get_client()
        await process_new_messages(client, start_id)
    except Exception as e:
        logger.error(f"Error processing Gmail notification: {e}", exc_info=True)

    return {"status": "ok"}


async def process_new_messages(client: GmailClient, start_history_id: str):
    import asyncio
    loop = asyncio.get_event_loop()

    logger.info(f"Fetching history since ID: {start_history_id}")

    try:
        history = await loop.run_in_executor(
            None,
            lambda: client._gmail.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                labelId="INBOX",
            ).execute()
        )
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        return

    logger.info(f"History response: {history}")

    records = history.get("history", [])
    if not records:
        logger.info("No new messages in history")
        return

    for record in records:
        for added in record.get("messagesAdded", []):
            msg_id = added["message"]["id"]
            labels = added["message"].get("labelIds", [])
            if "SENT" in labels:
                continue

            try:
                raw = await loop.run_in_executor(
                    None, lambda: client.get_message(msg_id)
                )
                parsed = parse_gmail_message(raw)
                assistant = client.assistant_email.lower()
                cc_list = [addr.lower() for addr in parsed.get("cc", [])]
                if assistant not in cc_list:
                    logger.info(f"Assistant not CC'd on {msg_id} — skipping")
                    continue

                logger.info(f"Processing: {parsed['subject']} from {parsed['from']}")
                await handle_gmail_scheduling(client, parsed)

            except Exception as e:
                logger.error(f"Error processing message {msg_id}: {e}", exc_info=True)


@router.post("/watch/setup")
async def setup_watch():
    topic = os.environ["PUBSUB_TOPIC"]
    client = get_client()
    result = client.setup_watch(topic)
    logger.info(f"Gmail watch set up: {result}")
    return result