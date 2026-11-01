"""
Email AI Assistant — Microsoft Graph webhook receiver
Receives push notifications when emails arrive in the assistant mailbox,
parses them, and routes to the appropriate handler (scheduling, etc.)
"""

import os
import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
import httpx

from app.graph_client import GraphClient
from app.email_parser import parse_email_notification
from app.scheduler import handle_scheduling_request
from app.ai_extractor import extract_scheduling_intent
from app.gmail_webhook import router as gmail_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Email AI Assistant")
app.include_router(gmail_router)

graph = GraphClient(
    tenant_id=os.environ["AZURE_TENANT_ID"],
    client_id=os.environ["AZURE_CLIENT_ID"],
    client_secret=os.environ["AZURE_CLIENT_SECRET"],
    assistant_email=os.environ["ASSISTANT_EMAIL"],  # e.g. assistant@yourcompany.com
)


# ── Webhook lifecycle ──────────────────────────────────────────────────────────

@app.get("/webhook")
async def webhook_validation(validationToken: str = Query(...)):
    """
    Microsoft Graph sends a GET with validationToken when you first register
    the subscription. Must echo it back as plain text within 10 seconds.
    """
    logger.info("Webhook validation handshake received")
    return PlainTextResponse(content=validationToken)


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Receives change notifications from Microsoft Graph when a new email
    arrives in the assistant mailbox.
    """
    # Validate the client state secret so we know it's really from Graph
    body = await request.json()

    for notification in body.get("value", []):
        client_state = notification.get("clientState", "")
        if client_state != os.environ["WEBHOOK_CLIENT_STATE"]:
            logger.warning("Invalid clientState on notification — ignoring")
            raise HTTPException(status_code=401, detail="Invalid client state")

        resource = notification.get("resource", "")
        logger.info(f"Notification for resource: {resource}")

        # Fetch the actual email from Graph (notification only gives us the ID)
        try:
            message_id = resource.split("/messages/")[-1]
            email = await graph.get_message(message_id)
            await process_email(email)
        except Exception as e:
            logger.error(f"Error processing notification: {e}", exc_info=True)
            # Return 200 anyway — Graph will retry on non-2xx

    return {"status": "ok"}


# ── Email processing ───────────────────────────────────────────────────────────

async def process_email(email: dict):
    """
    Central dispatcher: parse the email and route to the right handler.
    """
    parsed = parse_email_notification(email)
    logger.info(f"Processing email from {parsed['from']} | subject: {parsed['subject']}")

    # Use Claude to extract intent and details
    extracted = await extract_scheduling_intent(parsed)
    intent = extracted.get("intent", "none")
    logger.info(f"Detected intent: {intent}")

    if intent == "schedule":
        await handle_scheduling_request(graph, parsed)
    elif intent == "reschedule":
        await handle_scheduling_request(graph, parsed, reschedule=True)
    elif intent == "cancel":
        logger.info("Cancel intent detected — not yet implemented")
    else:
        logger.info("No actionable intent detected — no action taken")


# ── Subscription management ────────────────────────────────────────────────────

@app.post("/subscriptions/create")
async def create_subscription():
    """
    Register the Graph webhook subscription for the assistant mailbox.
    Call this once on startup (or renew it — subscriptions expire after 3 days).
    """
    notification_url = os.environ["WEBHOOK_PUBLIC_URL"] + "/webhook"
    expiry = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat().replace("+00:00", "Z")

    sub = await graph.create_subscription(
        notification_url=notification_url,
        expiry_datetime=expiry,
        client_state=os.environ["WEBHOOK_CLIENT_STATE"],
    )
    logger.info(f"Subscription created: {sub['id']} expires {sub['expirationDateTime']}")
    return sub


@app.post("/subscriptions/renew/{subscription_id}")
async def renew_subscription(subscription_id: str):
    """Renew an existing subscription before it expires (run daily via cron)."""
    expiry = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat().replace("+00:00", "Z")
    result = await graph.renew_subscription(subscription_id, expiry)
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
