"""
Parse a raw Microsoft Graph message object into a clean dict
the rest of the app works with.
"""

import re
from html import unescape
from html.parser import HTMLParser


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []

    def handle_data(self, data):
        self.text_parts.append(data)

    def get_text(self):
        return " ".join(self.text_parts)


def html_to_text(html: str) -> str:
    """Strip HTML tags and decode entities."""
    stripper = _HTMLStripper()
    stripper.feed(unescape(html))
    return re.sub(r"\s+", " ", stripper.get_text()).strip()


def parse_email_notification(message: dict) -> dict:
    """
    Turn a Graph message object into a flat dict with the fields we care about.

    Returns:
        {
            "id": str,
            "subject": str,
            "from": str,           # email address
            "from_name": str,
            "to": [str],           # list of email addresses
            "cc": [str],
            "body": str,           # plain text
            "body_html": str,
            "received_at": str,    # ISO 8601
        }
    """
    def addr(obj):
        return obj.get("emailAddress", {}).get("address", "").lower()

    def name(obj):
        return obj.get("emailAddress", {}).get("name", "")

    body_content = message.get("body", {}).get("content", "")
    body_type = message.get("body", {}).get("contentType", "text")

    if body_type.lower() == "html":
        body_text = html_to_text(body_content)
        body_html = body_content
    else:
        body_text = body_content
        body_html = ""

    sender = message.get("from", {})

    return {
        "id": message.get("id", ""),
        "subject": message.get("subject", ""),
        "from": addr(sender),
        "from_name": name(sender),
        "to": [addr(r) for r in message.get("toRecipients", [])],
        "cc": [addr(r) for r in message.get("ccRecipients", [])],
        "body": body_text,
        "body_html": body_html,
        "received_at": message.get("receivedDateTime", ""),
    }
