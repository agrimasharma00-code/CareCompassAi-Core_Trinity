"""Best-effort Twilio booking notifications, isolated from booking persistence."""

import logging
import re
from contextvars import ContextVar, Token
from functools import lru_cache
from typing import Any

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import settings


logger = logging.getLogger(__name__)
_skip_warning_logged = False
_booking_sms_recipient: ContextVar[str | None] = ContextVar("booking_sms_recipient", default=None)


def set_booking_sms_recipient(value: str | None) -> Token[str | None]:
    """Keep the optional request header out of booking persistence and responses."""
    return _booking_sms_recipient.set(value)


def reset_booking_sms_recipient(token: Token[str | None]) -> None:
    _booking_sms_recipient.reset(token)


def current_booking_sms_recipient() -> str | None:
    return _booking_sms_recipient.get()


def _masked(number: str) -> str:
    return f"***{number[-4:]}" if len(number) >= 4 else "***"


def _warn_skip(reason: str) -> None:
    global _skip_warning_logged
    if not _skip_warning_logged:
        logger.warning("Booking SMS skipped: %s", reason)
        _skip_warning_logged = True


def normalize_recipient(value: str | None) -> str | None:
    """Normalise an Indian local number (or supplied E.164 value) without logging it."""
    if not value:
        return None
    compact = re.sub(r"[\s().-]", "", value)
    if compact.startswith("+"):
        candidate = compact
    else:
        country = settings.sms_default_country_code.strip() or "+91"
        country = country if country.startswith("+") else f"+{country}"
        candidate = f"{country}{compact.lstrip('0')}"
    return candidate if re.fullmatch(r"\+\d{7,15}", candidate) else None


@lru_cache(maxsize=1)
def _client() -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def _message_body(booking: dict[str, Any]) -> str:
    name = str(booking.get("patient_name") or "there")
    reference = str(booking.get("id") or "your booking")
    return f"Hi {name}, your appointment request is confirmed. Ref: {reference}."


def send_booking_sms(to: str, booking: dict[str, Any]) -> None:
    """Send one background SMS; all failures are logged and intentionally swallowed."""
    if not settings.sms_enabled:
        _warn_skip("SMS_ENABLED is false")
        return
    if not all((settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_phone_number)):
        _warn_skip("Twilio credentials or sender number are missing")
        return
    recipient = normalize_recipient(to)
    if not recipient:
        logger.warning("Booking SMS skipped: invalid recipient %s", _masked(to or ""))
        return
    try:
        message = _client().messages.create(
            to=recipient,
            from_=settings.twilio_phone_number,
            body=_message_body(booking),
        )
        logger.info("Booking SMS sent sid=%s recipient=%s", message.sid, _masked(recipient))
    except TwilioRestException as error:
        logger.warning("Booking SMS failed code=%s message=%s recipient=%s", error.code, error.msg, _masked(recipient))
    except Exception as error:  # The notification must never affect a confirmed booking.
        logger.warning("Booking SMS failed error=%s recipient=%s", error, _masked(recipient))
