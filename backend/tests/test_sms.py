import asyncio
from types import SimpleNamespace

import pytest
from app.api import bookings
from app.services import sms


BOOKING = {
    "id": "BK-SMS01",
    "status": "pending",
    "patient_name": "Demo patient",
    "caregiver_id": "CG_001",
    "care_type": "gp_teleconsult",
    "urgency": "routine",
    "summary": "Demo booking",
}


def configure_sms(monkeypatch: pytest.MonkeyPatch, *, enabled: bool = True, credentials: bool = True) -> None:
    monkeypatch.setattr(sms.settings, "sms_enabled", enabled)
    monkeypatch.setattr(sms.settings, "twilio_account_sid", "AC-test" if credentials else None)
    monkeypatch.setattr(sms.settings, "twilio_auth_token", "token-test" if credentials else None)
    monkeypatch.setattr(sms.settings, "twilio_phone_number", "+14475550123" if credentials else None)
    monkeypatch.setattr(sms.settings, "sms_default_country_code", "+91")
    sms._client.cache_clear()
    sms._skip_warning_logged = False


def test_send_booking_sms_uses_twilio_for_a_successful_booking(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_sms(monkeypatch)
    sent: list[dict[str, str]] = []

    class FakeMessages:
        def create(self, **kwargs: str) -> SimpleNamespace:
            sent.append(kwargs)
            return SimpleNamespace(sid="SM-test")

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(sms, "Client", lambda *_: FakeClient())
    sms.send_booking_sms("98765 43210", BOOKING)
    assert sent == [{"to": "+919876543210", "from_": "+14475550123", "body": "Hi Demo patient, your appointment request is confirmed. Ref: BK-SMS01."}]


def test_booking_failure_does_not_schedule_sms(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        sent: list[tuple[object, ...]] = []
        def fail_booking(_: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(bookings, "create_booking", fail_booking)
        monkeypatch.setattr(bookings, "send_booking_sms", lambda *args: sent.append(args))
        token = sms.set_booking_sms_recipient("+919876543210")
        with pytest.raises(RuntimeError, match="database unavailable"):
            await bookings.book(bookings.BookingCreate(**{key: BOOKING[key] for key in ("caregiver_id", "patient_name", "care_type", "urgency", "summary")}))
        sms.reset_booking_sms_recipient(token)
        assert sent == []

    asyncio.run(run())


def test_booking_succeeds_when_background_twilio_call_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        configure_sms(monkeypatch)

        class FailingMessages:
            def create(self, **_: str) -> None:
                raise RuntimeError("Twilio unavailable")

        class FailingClient:
            messages = FailingMessages()

        async def no_publish(*_: object, **__: object) -> None:
            return None

        monkeypatch.setattr(sms, "Client", lambda *_: FailingClient())
        monkeypatch.setattr(bookings, "create_booking", lambda _: BOOKING.copy())
        monkeypatch.setattr(bookings.hub, "publish", no_publish)
        scheduled: list[object] = []
        monkeypatch.setattr(bookings.asyncio, "create_task", lambda task: scheduled.append(task))
        token = sms.set_booking_sms_recipient("+919876543210")
        created = await bookings.book(bookings.BookingCreate(**{key: BOOKING[key] for key in ("caregiver_id", "patient_name", "care_type", "urgency", "summary")}))
        sms.reset_booking_sms_recipient(token)
        assert created == BOOKING
        assert len(scheduled) == 1
        await scheduled[0]

    asyncio.run(run())


@pytest.mark.parametrize(("enabled", "credentials"), [(False, True), (True, False)])
def test_sms_is_skipped_when_disabled_or_unconfigured(monkeypatch: pytest.MonkeyPatch, enabled: bool, credentials: bool) -> None:
    configure_sms(monkeypatch, enabled=enabled, credentials=credentials)
    monkeypatch.setattr(sms, "Client", lambda *_: pytest.fail("Twilio client should not be created"))
    sms.send_booking_sms("9876543210", BOOKING)
