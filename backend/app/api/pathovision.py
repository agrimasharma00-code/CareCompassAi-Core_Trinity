"""PathoVision: privacy-first, non-diagnostic upload guidance.

Uploads are kept in memory for one request only. This module intentionally never writes
the supplied bytes, image pixels, OCR text, or model output to disk or logs.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.voice import _sarvam_audio_reply
from app.config import settings
from app.core.red_flags import find_red_flags
from app.core.voice_agent import language_from_text
from app.schemas.care import Language


router = APIRouter(prefix="/api/v1/pathovision", tags=["pathovision"])
MAX_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 5
DISCLAIMER = "PathoVision gives information, not a diagnosis. For emergencies call 112."
WOUND_STEPS = [
    "Apply firm pressure with a clean cloth if there is bleeding.",
    "Rinse the area gently with clean running water.",
    "Cover it with a clean dressing.",
    "Keep the area raised if possible.",
    "Ask a doctor whether tetanus vaccination is up to date.",
]
WOUND_WARNINGS = [
    "Bleeding does not stop after 10 minutes of firm pressure, or blood spurts.",
    "The wound is deep, gaping, or shows fat, bone, tendon, or an object stuck in it.",
    "It was caused by an animal or human bite, or involves the head or eye.",
    "There is numbness, loss of movement, spreading redness, pus, or fever.",
    "The cause was very dirty or rusty.",
]
_LAB_ROW = re.compile(
    r"^\s*(?P<test>[A-Za-z][A-Za-z0-9 ()/%+._-]{1,55}?)\s+"
    r"(?P<value>-?\d+(?:\.\d+)?)\s*"
    r"(?P<unit>[A-Za-zµμ/%^0-9.-]{0,18})?\s*"
    r"(?P<range>-?\d+(?:\.\d+)?\s*(?:-|–|to)\s*-?\d+(?:\.\d+)?)\s*$"
)


def _language_text(language: Language, english: str, hindi: str, hinglish: str) -> str:
    if language == Language.HI:
        return hindi
    if language == Language.HINGLISH:
        return hinglish
    return english


def _kind_from_bytes(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    # HEIC/HEIF are ISO-BMFF files. Pillow needs an HEIF decoder plug-in to open them.
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in {b"heic", b"heix", b"hevc", b"hevx", b"mif1"}:
        return "image/heic"
    return None


def _dependency_error(name: str, install: str) -> HTTPException:
    return HTTPException(status_code=503, detail=f"{name} is not installed on this server. Install it with: {install}")


def _prepared_jpeg(data: bytes) -> tuple[bytes, str]:
    """Strip EXIF/GPS and constrain the image entirely in memory."""
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise _dependency_error("Pillow", "pip install pillow") from error
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1280, 1280))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            return output.getvalue(), "image/jpeg"
    except Exception as error:
        raise HTTPException(status_code=415, detail="The image could not be read. Try a clear JPG, PNG, or WEBP file.") from error


def _ocr_image(image_bytes: bytes) -> tuple[str, list[dict[str, Any]]]:
    if settings.ocr_engine.casefold() != "tesseract":
        raise HTTPException(status_code=503, detail="OCR_ENGINE is not supported. Set OCR_ENGINE=tesseract or configure a supported hosted OCR provider.")
    try:
        from PIL import Image, ImageOps
        import pytesseract
    except ImportError as error:
        raise _dependency_error("OCR dependencies", "pip install pillow pytesseract") from error
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    try:
        with Image.open(io.BytesIO(image_bytes)) as raw:
            image = ImageOps.autocontrast(ImageOps.grayscale(raw))
            image = image.point(lambda value: 255 if value > 165 else 0)
            data = pytesseract.image_to_data(image, lang="eng+hin", output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError as error:
        raise HTTPException(status_code=503, detail="Tesseract is not available. Install Tesseract and set TESSERACT_CMD on Windows.") from error
    except Exception as error:
        raise HTTPException(status_code=422, detail="OCR could not read this file. Try a brighter, sharper image.") from error
    lines: list[dict[str, Any]] = []
    words: list[str] = []
    for word, confidence in zip(data.get("text", []), data.get("conf", []), strict=False):
        clean = str(word).strip()
        if not clean:
            continue
        try:
            score = float(confidence)
        except (TypeError, ValueError):
            score = -1
        words.append(clean)
        lines.append({"text": clean, "confidence": max(score, 0), "needs_review": score < 65})
    return " ".join(words), lines


def _extract_pdf(data: bytes) -> tuple[str, list[dict[str, Any]]]:
    try:
        import pymupdf
    except ImportError as error:
        raise _dependency_error("PyMuPDF", "pip install pymupdf") from error
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
        pages = list(document)[:MAX_PDF_PAGES]
        embedded = "\n".join(page.get_text("text") for page in pages).strip()
        if len(embedded) >= 24:
            return embedded, []
        ocr_text: list[str] = []
        ocr_lines: list[dict[str, Any]] = []
        for page in pages:
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            text, lines = _ocr_image(pixmap.tobytes("png"))
            ocr_text.append(text)
            ocr_lines.extend(lines)
        return "\n".join(ocr_text).strip(), ocr_lines
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=422, detail="This PDF could not be read. Upload a non-password-protected report with up to five pages.") from error


def _status(value: float, reference: str) -> str:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", reference)
    if len(numbers) != 2:
        return "unclear"
    low, high = map(float, numbers)
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "normal"


def _report_table(text: str, ocr_lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    low_confidence = any(line["needs_review"] for line in ocr_lines)
    rows: list[dict[str, Any]] = []
    for raw in text.splitlines():
        match = _LAB_ROW.match(raw)
        if not match:
            continue
        value = float(match.group("value"))
        reference = match.group("range").replace("to", "–")
        rows.append({
            "test": match.group("test").strip(),
            "value": match.group("value"),
            "unit": (match.group("unit") or "").strip(),
            "reference_range": reference,
            "status": _status(value, reference),
            "meaning_in_plain_words": "This is a measurement listed on the report; a clinician can explain what it means for you.",
            "confidence": "low" if low_confidence else "high",
        })
    return rows


def _emergency_result(language: Language, labels: list[str]) -> dict[str, Any]:
    explanation = _language_text(
        language,
        "Your note includes a possible emergency warning sign. Please call 112 now. Do not wait for image analysis.",
        "आपके नोट में संभावित आपात संकेत है। कृपया अभी 112 पर कॉल करें। छवि विश्लेषण की प्रतीक्षा न करें।",
        "Aapke note mein possible emergency warning sign hai. Kripya abhi 112 call karein; image analysis ka wait na karein.",
    )
    return {
        "kind": "emergency", "image_quality": "not assessed", "findings": [], "extracted_text": "", "lab_table": [],
        "first_aid_steps": WOUND_STEPS, "when_to_get_help": WOUND_WARNINGS, "red_flags": labels,
        "care_type": "emergency_112", "urgency": "emergency", "reasoning": explanation,
        "plain_explanation": explanation, "disclaimers": [DISCLAIMER], "model": "rules", "language": language.value,
    }


async def _vision_json(image: bytes, mime_type: str, language: Language, note: str) -> dict[str, Any]:
    prompt = """Classify this medical-related image as wound_photo, medical_report, xray_or_scan_image, prescription, other_medical, not_medical, or unclear. Do not diagnose, prescribe, or name a disease. For wound_photo, describe only visible facts and standard first-aid. For xray_or_scan_image, refuse interpretation and ask for a radiologist written report. Return only JSON with: kind, image_quality, findings (array of strings), severity_signals (array), plain_explanation, care_type, urgency."""
    encoded = base64.b64encode(image).decode("ascii")
    if settings.openai_api_key:
        payload = {"model": settings.openai_vision_model, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": [{"type": "text", "text": f"Language: {language.value}. User note: {note}"}, {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}}]}], "max_tokens": 700}
        headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail="The configured vision provider could not analyse this image.")
            content = response.json()["choices"][0]["message"]["content"]
    elif settings.anthropic_api_key:
        payload = {"model": settings.anthropic_vision_model, "max_tokens": 700, "system": prompt, "messages": [{"role": "user", "content": [{"type": "text", "text": f"Language: {language.value}. User note: {note}"}, {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": encoded}}]}]}
        headers = {"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail="The configured vision provider could not analyse this image.")
            content = response.json()["content"][0]["text"]
    else:
        raise HTTPException(status_code=503, detail="No vision provider is configured. Add OPENAI_API_KEY or ANTHROPIC_API_KEY on the backend; Sarvam text models cannot interpret images.")
    try:
        return json.loads(str(content).strip().removeprefix("```json").removesuffix("```").strip())
    except (TypeError, ValueError, KeyError) as error:
        raise HTTPException(status_code=502, detail="The vision provider returned an unreadable result. Please try again.") from error


@router.post("")
async def analyse_pathovision(
    file: UploadFile = File(...),
    lang: Language = Form(Language.AUTO),
    note: str = Form("", max_length=1200),
) -> dict[str, Any]:
    """Analyse a single upload in memory. Never persist upload content or OCR/model output."""
    started = time.monotonic()
    content = await file.read(MAX_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Choose a JPG, PNG, WEBP, HEIC, or PDF file to analyse.")
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="This file is larger than 8 MB. Choose a smaller image or PDF.")
    file_kind = _kind_from_bytes(content)
    if not file_kind:
        raise HTTPException(status_code=415, detail="Unsupported file. Upload a real JPG, PNG, WEBP, HEIC, or PDF—not a renamed file.")
    language = language_from_text(note, lang)
    note_flags = find_red_flags(note)
    if note_flags:
        result = _emergency_result(language, note_flags)
    elif file_kind == "pdf":
        extracted, ocr_lines = _extract_pdf(content)
        if not extracted:
            raise HTTPException(status_code=422, detail="No readable report text was found. Upload a brighter, sharper scan.")
        table = _report_table(extracted, ocr_lines)
        result = {
            "kind": "medical_report", "image_quality": "needs review" if ocr_lines else "readable", "findings": [],
            "extracted_text": extracted[:12000], "lab_table": table, "first_aid_steps": [], "when_to_get_help": [],
            "red_flags": [], "care_type": "teleconsultation" if any(row["status"] in {"low", "high"} for row in table) else None,
            "urgency": "same_day" if any(row["status"] in {"low", "high"} for row in table) else "scheduled",
            "reasoning": "Values are compared only with the printed ranges in this report.",
            "plain_explanation": "Here are the report values and their printed ranges. Please show this report to your doctor.",
            "questions_for_doctor": ["Which values should I discuss first?", "Do any results need a repeat test?"],
            "ocr_lines": ocr_lines, "disclaimers": [DISCLAIMER, "Please show this report to your doctor."], "model": "pdf-text-or-ocr", "language": language.value,
        }
    else:
        if file_kind == "image/heic":
            raise HTTPException(status_code=415, detail="HEIC needs an installed server-side HEIF decoder. Convert it to JPG or PNG and try again.")
        prepared, mime_type = _prepared_jpeg(content)
        vision = await _vision_json(prepared, mime_type, language, note)
        kind = str(vision.get("kind", "unclear"))
        if kind == "xray_or_scan_image":
            vision.update({"findings": [], "plain_explanation": "I cannot interpret X-ray, CT, or MRI images. Please upload the radiologist's written report and I can explain its text in plain words.", "care_type": "teleconsultation", "urgency": "scheduled"})
        result = {"kind": kind, "image_quality": str(vision.get("image_quality", "review needed")), "findings": vision.get("findings", []), "extracted_text": "", "lab_table": [], "first_aid_steps": WOUND_STEPS if kind == "wound_photo" else [], "when_to_get_help": WOUND_WARNINGS if kind == "wound_photo" else [], "red_flags": vision.get("severity_signals", []), "care_type": vision.get("care_type"), "urgency": vision.get("urgency"), "reasoning": vision.get("plain_explanation", ""), "plain_explanation": vision.get("plain_explanation", ""), "disclaimers": [DISCLAIMER], "model": "vision-provider", "language": language.value}
    spoken = await _sarvam_audio_reply(str(result["plain_explanation"]), "hi-IN" if language == Language.HI else "en-IN")
    result["audio_base64"] = spoken
    result["audio_mime_type"] = "audio/wav" if spoken else None
    # Metadata only: no file bytes, text, or model response is logged or stored.
    result["processing_ms"] = int((time.monotonic() - started) * 1000)
    return result
