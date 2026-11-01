"""
Parse a raw Gmail API message object into the same clean dict
the rest of the app uses — identical shape to email_parser.py's output
so scheduler.py and ai_extractor.py work unchanged.
"""

import base64
import re
from html import unescape
from html.parser import HTMLParser


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return " ".join(self.parts)


def html_to_text(html: str) -> str:
    s = _HTMLStripper()
    s.feed(unescape(html))
    return re.sub(r"\s+", " ", s.get_text()).strip()


def _header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode_body(part: dict) -> tuple[str, str]:
    """Return (plain_text, html) from a message part."""
    mime = part.get("mimeType", "")
    data = part.get("body", {}).get("data", "")
    if not data:
        return "", ""
    decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    if mime == "text/html":
        return html_to_text(decoded), decoded
    return decoded, ""


def _extract_body(payload: dict) -> tuple[str, str]:
    """Recursively extract plain text and HTML from a Gmail message payload."""
    mime = payload.get("mimeType", "")
    parts = payload.get("parts", [])

    if not parts:
        return _decode_body(payload)

    plain, html = "", ""
    for part in parts:
        p, h = _extract_body(part)
        plain = plain or p
        html = html or h

    return plain, html


def _parse_address(header_value: str) -> list[str]:
    """Extract email addresses from a header like 'Name <email>, Name2 <email2>'."""
    return [m.lower() for m in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", header_value)]


def parse_gmail_message(message: dict) -> dict:
    """
    Turn a Gmail API message object into the same flat dict
    that the rest of the app expects.
    """
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    subject = _header(headers, "Subject")
    from_raw = _header(headers, "From")
    to_raw = _header(headers, "To")
    cc_raw = _header(headers, "Cc")
    date = _header(headers, "Date")

    from_addrs = _parse_address(from_raw)
    from_email = from_addrs[0] if from_addrs else ""
    from_name = re.sub(r"<.*?>", "", from_raw).strip().strip('"')

    body_text, body_html = _extract_body(payload)

    return {
        "id": message.get("id", ""),
        "thread_id": message.get("threadId", ""),
        "subject": subject,
        "from": from_email,
        "from_name": from_name,
        "to": _parse_address(to_raw),
        "cc": _parse_address(cc_raw),
        "body": body_text,
        "body_html": body_html,
        "received_at": date,
    }
