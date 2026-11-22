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
# Track the last processed history ID to avoid re-processing
_last_history_id: str = None


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
    global _last_history_id

    body = await request.json()

    # Decode the Pub/Sub message
    pubsub_message = body.get("message", {})
    data_b64 = pubs    data_b64 = pubs    data_b64 = pubs    data_b64 = pubreturn {    data:     data_b64      data_jso    data_b6e64.b64decode(data_b64).decode("utf-8"))
    email_address = data.get("emailAddress")    email_address = data.get("emailAddress")   gger.info(f"Gmail notification for {email_address}, historyId: {history_id}")

    # Use the previous history ID as startHistoryId so we get the new messages
    start_id = _last_history_id or s    start_id = _last_history_id or s    start_id = _last_hi    try:
        client = get_cli        client = get_cli       _m        client = ta        client = get_cpt        client = get_cli      (f"Error processing Gmail notification: {e}", exc_info=True)

    return {"status": "ok"}


async def process_new_messages(client: GmailClient, start_history_id: str):
    """
    Fetch messages added since the last history ID and process each one.
    """
    import asyncio

    loop = asyncio.get_event_loop()

    try:
        history = await loop.run_in_executor(
                                                                                                                                                                          hi                                                                                                                                                                       ry:                                                                             co                                                                                                                                                                                                                                                                                  hi                 age"].get("labelIds", [])
                                                                                                                                                                  ient.get_message(msg_id)
                )
                parsed = parse_gmail_message(raw)

                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i          l                 # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                # Only act i                #tch(topic)
    logger.info(f"Gmail watch set up: {result}")
    return result
