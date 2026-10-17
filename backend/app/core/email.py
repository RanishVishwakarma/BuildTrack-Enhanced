"""Minimal outgoing email. Disabled (logs only) unless SMTP_* settings are set."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def email_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from_email)


def send_email(*, to_email: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns False (never raises) when not sent."""
    if not email_configured():
        logger.info("SMTP is not configured; email '%s' not sent", subject)
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=12) as server:
            server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
        return True
    except Exception:
        logger.exception("Sending email '%s' failed", subject)
        return False
