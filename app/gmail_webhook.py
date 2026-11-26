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

# Single shared client instance
_client: GmailClient = None
# Track the last processed history ID per email address to avoid re-processing
_last_history_ids: dict = {}


def get_client() -> GmailClient:
    global _client
    if _client is None:
        _client = GmailClient()
    return _client


@router.post("/webhook")
async def gmail_webhook(request: Request):
    """
    Google Pub/Sub pushes a POST here when a new email arrives.
    The body contains a base64-encoded Gmail notification.
    """
    global _last_history_ids

    body = await request.json()

    # Decode the Pub/Sub message
    pubsub_message = body.get("message", {})
    data_b64 = pubsub_message.get("data", "")
    if not data_b64:
        return {"status": "no data"}

    data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    email_address = data.get("emailAddress")
    history_id = data.get("historyId")

    logger.info(f"Gmail notification for {email_address}, historyId: {history_id}")

    # Only process notifications for the assistant's own account
    client = get_client()
    if email_address and email_address.lower() != client.assistant_email.lower():
        logger.info(f"Ignoring notification for {email_address} (not assistant account)")
        return {"status": "ignored"}

    # Use the previous history ID as startHistoryId so we get the new messages
    start_id = _last_history_ids.get(email_address) or str(int(history_id) - 1)
    _last_history_ids[email_address] = history_id

    try:
        await process_new_messages(client, start_id)
    except Exception as e:
        logger.error(f"Error processing Gmail notification: {e}", exc_info=True)

    return {"status": "ok"}


async def process_new_messages(client: GmailClient, start_history_id: str):
    """
    Fetch messages added since the last history ID and process each one.
    """
    import asyncio

    loop = asyncio.get_event_loop()

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

    records = history.get("history", [])
    if not records:
        logger.info("No new messages in history")
        return

    for record in records:
        for added in record.get("messagesAdded", []):
            msg_id = added["message"]["id"]

            # Skip messages sent BY the assistant (avoid loops)
            labels = added["message"].get("labelIds", [])
            if "SENT" in labels:
                continue

            try:
                raw = await loop.run_in_executor(
                    None, lambda: client.get_message(msg_id)
                )
                parsed = parse_gmail_message(raw)

                # Only act if assistant is CC'd, not the primary recipient
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
    """
    Register Gmail push notifications to your Pub/Sub topic.
    Call once, then renew every 7 days (Gmail watch expires).
    """
    topic = os.environ["PUBSUB_TOPIC"]  # projects/{id}/topics/{name}
    client = get_client()
    result = client.setup_watch(topic)
    logger.info(f"Gmail watch set up: {result}")
    return result