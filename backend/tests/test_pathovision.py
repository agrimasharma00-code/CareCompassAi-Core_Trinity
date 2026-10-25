"""Focused safety and parsing tests for PathoVision's in-memory workflow."""

import io

import pytest

from app.api import pathovision
from app.schemas.care import Language


def test_magic_bytes_accept_only_supported_uploads() -> None:
    assert pathovision._kind_from_bytes(b"\xff\xd8\xffrest") == "image/jpeg"
    assert pathovision._kind_from_bytes(b"MZ-not-an-image") is None
    assert pathovision._kind_from_bytes(b"%PDF-1.7") == "pdf"


def test_report_parser_marks_only_printed_reference_ranges() -> None:
    report = """Hemoglobin 10.2 g/dL 12.0-16.0
Glucose 92 mg/dL 70-100
Creatinine 1.8 mg/dL 0.6-1.2"""
    rows = pathovision._report_table(report, [])
    assert [row["status"] for row in rows] == ["low", "normal", "high"]
    assert all("clinician" in row["meaning_in_plain_words"].lower() for row in rows)


def test_pdf_with_embedded_text_is_read_in_memory() -> None:
    reportlab = pytest.importorskip("reportlab.pdfgen.canvas", reason="reportlab is needed for the synthetic PDF test")
    document = io.BytesIO()
    pdf = reportlab.Canvas(document)
    pdf.drawString(60, 760, "Hemoglobin 10.2 g/dL 12.0-16.0")
    pdf.drawString(60, 735, "Glucose 92 mg/dL 70-100")
    pdf.drawString(60, 710, "Creatinine 1.8 mg/dL 0.6-1.2")
    pdf.save()
    text, lines = pathovision._extract_pdf(document.getvalue())
    assert "Hemoglobin" in text
    assert lines == []
    assert [row["status"] for row in pathovision._report_table(text, lines)] == ["low", "normal", "high"]


def test_note_red_flag_can_be_resolved_before_vision_call() -> None:
    labels = pathovision.find_red_flags("I have chest pain and feel dizzy")
    assert labels
    result = pathovision._emergency_result(Language.EN, labels)
    assert result["care_type"] == "emergency_112"
    assert result["urgency"] == "emergency"
    assert result["model"] == "rules"
