"""Optional Resend delivery; failures never interrupt the primary notification."""

import logging
import os
import re

import requests
from dotenv import load_dotenv

logger = logging.getLogger("drophunter.email")


def validate_email(address: str) -> str:
    address = address.strip()
    if len(address) > 254 or not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", address):
        raise ValueError("Enter a valid email address, such as you@example.com.")
    return address


def send_email(to: str, subject: str, html: str, text: str | None = None) -> bool:
    try:
        load_dotenv()
        key = os.environ.get("RESEND_API_KEY")
        sender = os.environ.get("EMAIL_FROM")
        if not key or not sender:
            return False
        payload = {"from": sender, "to": [validate_email(to)], "subject": subject, "html": html}
        if text is not None:
            payload["text"] = text
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Email delivery failed (%s)", type(exc).__name__)
        return False
