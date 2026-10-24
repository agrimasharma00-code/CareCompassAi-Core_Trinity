"""Small SQLite-backed demo state for bookings and emergency dispatch."""

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "niramaya_demo.sqlite3"


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS bookings (id TEXT PRIMARY KEY, caregiver_id TEXT, patient_name TEXT, care_type TEXT, urgency TEXT, summary TEXT, status TEXT, created_at TEXT)")
    connection.execute("CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY, patient_name TEXT, summary TEXT, red_flags TEXT, latitude REAL, longitude REAL, status TEXT, created_at TEXT)")
    return connection


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_booking(payload: dict[str, Any]) -> dict[str, Any]:
    booking = {"id": f"BK-{uuid.uuid4().hex[:6].upper()}", "status": "pending", "created_at": _now(), **payload}
    with _connection() as connection:
        connection.execute("INSERT INTO bookings VALUES (:id, :caregiver_id, :patient_name, :care_type, :urgency, :summary, :status, :created_at)", booking)
    return booking


def list_bookings() -> list[dict[str, Any]]:
    with _connection() as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM bookings ORDER BY created_at DESC")]


def update_booking(booking_id: str, status: str) -> dict[str, Any] | None:
    with _connection() as connection:
        connection.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))
        row = connection.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    return dict(row) if row else None


def create_alert(payload: dict[str, Any]) -> dict[str, Any]:
    alert = {"id": f"AL-{uuid.uuid4().hex[:6].upper()}", "status": "new", "created_at": _now(), **payload}
    alert["red_flags"] = json.dumps(alert.get("red_flags", []))
    with _connection() as connection:
        connection.execute("INSERT INTO alerts VALUES (:id, :patient_name, :summary, :red_flags, :latitude, :longitude, :status, :created_at)", alert)
    alert["red_flags"] = json.loads(alert["red_flags"])
    return alert


def list_alerts() -> list[dict[str, Any]]:
    with _connection() as connection:
        alerts = [dict(row) for row in connection.execute("SELECT * FROM alerts ORDER BY created_at DESC")]
    for alert in alerts:
        alert["red_flags"] = json.loads(alert["red_flags"])
    return alerts


def update_alert(alert_id: str, status: str) -> dict[str, Any] | None:
    with _connection() as connection:
        connection.execute("UPDATE alerts SET status = ? WHERE id = ?", (status, alert_id))
        row = connection.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    if not row:
        return None
    alert = dict(row); alert["red_flags"] = json.loads(alert["red_flags"])
    return alert
