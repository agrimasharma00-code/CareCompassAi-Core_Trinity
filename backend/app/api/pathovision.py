"""PathoVision: privacy-first, non-diagnostic upload guidance.

Uploads are kept in memory for one request only. This module intentionally never writes
the supplied bytes, image pixels, OCR text, or model output to disk or logs.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
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
logger = logging.getLogger(__name__)
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
        languages = pytesseract.get_languages(config="")
        if "hin" not in languages:
            raise HTTPException(
                status_code=503,
                detail="Tesseract Hindi data (hin.traineddata) is missing. Install it in Tesseract's tessdata folder, then retry.",
            )
        with Image.open(io.BytesIO(image_bytes)) as raw:
            image = ImageOps.autocontrast(ImageOps.grayscale(raw))
            if max(image.size) < 1600:
                image = image.resize((image.width * 2, image.height * 2))
            image = image.point(lambda value: 255 if value > 165 else 0)
            data = pytesseract.image_to_data(image, lang="eng+hin", output_type=pytesseract.Output.DICT)
    except HTTPException:
        raise
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
    match = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(-?\d+(?:\.\d+)?)\s*$", reference)
    if not match:
        return "unclear"
    low, high = map(float, match.groups())
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


def _json_from_model(content: str) -> dict[str, Any]:
    """Models occasionally wrap JSON in prose or a code fence; accept the first object."""
    clean = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content.strip(), flags=re.IGNORECASE)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", clean):
        try:
            parsed, _ = decoder.raw_decode(clean[match.start():])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise ValueError("No JSON object found")


def _provider_detail(response: httpx.Response) -> str:
    """Return a readable provider error without exposing credentials or body content."""
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
        if message:
            return str(message)[:280]
    except (TypeError, ValueError):
        pass
    return f"HTTP {response.status_code}"


async def _vision_json(image: bytes, mime_type: str, language: Language, note: str) -> dict[str, Any]:
    """Send an in-memory JPEG to an OpenAI-compatible endpoint, including Gemini."""
    prompt = f"""Return JSON only and use {language.value}. Classify this image as wound_photo, medical_report, xray_or_scan_image, prescription, not_medical, or unclear. Do not diagnose, name a disease, prescribe, recommend medicine, cream, antibiotic, or dosage. For a wound, describe only visible colour, edges, swelling, discharge, dirt, and size only if a reference object is visible. Set severity to mild, moderate, severe, or unclear. For an X-ray, CT, or MRI, refuse image interpretation and request the written radiologist report. For unclear images, request a better photo. User note: {note or '(none)'}. JSON keys: kind, image_quality, findings (array), severity, severity_signals (array), plain_explanation, care_type, urgency."""
    encoded = base64.b64encode(image).decode("ascii")
    if settings.openai_api_key:
        model = settings.openai_vision_model or settings.openai_model
        payload = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": "Analyse this uploaded file safely."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                ]},
            ],
            "max_tokens": 850,
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
        endpoint = f"{settings.openai_base.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=max(settings.pathovision_timeout_s, 45.0)) as client:
            for attempt in range(3):
                try:
                    response = await client.post(endpoint, headers=headers, json=payload)
                except httpx.HTTPError as error:
                    if attempt == 2:
                        raise HTTPException(status_code=503, detail="Vision service is unavailable. Please try again shortly.") from error
                    await asyncio.sleep(2 ** attempt)
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise HTTPException(status_code=503, detail="Vision service is busy. Please try again in a minute.")
                if response.status_code >= 400:
                    raise HTTPException(status_code=502, detail=f"Vision provider rejected this request: {_provider_detail(response)}")
                try:
                    content = response.json()["choices"][0]["message"]["content"]
                    return _json_from_model(str(content))
                except (KeyError, IndexError, TypeError, ValueError) as error:
                    raise HTTPException(status_code=502, detail="Vision provider returned an unreadable result. Please try another clear image.") from error
    elif settings.anthropic_api_key:
        payload = {"model": settings.anthropic_vision_model, "max_tokens": 850, "system": prompt, "messages": [{"role": "user", "content": [{"type": "text", "text": f"Language: {language.value}. User note: {note}"}, {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": encoded}}]}]}
        headers = {"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        async with httpx.AsyncClient(timeout=max(settings.pathovision_timeout_s, 45.0)) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Vision provider rejected this request: {_provider_detail(response)}")
        try:
            return _json_from_model(str(response.json()["content"][0]["text"]))
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise HTTPException(status_code=502, detail="Vision provider returned an unreadable result. Please try another clear image.") from error
    raise HTTPException(status_code=503, detail="Vision service is not configured. Set OPENAI_API_KEY (and OPENAI_BASE for Gemini) or ANTHROPIC_API_KEY. Sarvam text models cannot interpret images.")


@router.get("/diag")
async def pathovision_diagnostics() -> dict[str, Any]:
    """Report PathoVision readiness without reading, storing, or logging a user upload."""
    checks: dict[str, dict[str, str | bool]] = {}
    try:
        import pytesseract
        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        version = str(pytesseract.get_tesseract_version()).splitlines()[0]
        languages = pytesseract.get_languages(config="")
        checks["tesseract"] = {"ok": True, "detail": version}
        checks["tesseract_hindi"] = {"ok": "hin" in languages, "detail": "hin language data found" if "hin" in languages else "Install hin.traineddata in Tesseract's tessdata folder."}
    except Exception:
        checks["tesseract"] = {"ok": False, "detail": "Tesseract was not found. Install it and set TESSERACT_CMD on Windows."}
        checks["tesseract_hindi"] = {"ok": False, "detail": "Hindi OCR cannot run until Tesseract and hin.traineddata are installed."}
    try:
        import fitz  # noqa: F401
        checks["pymupdf"] = {"ok": True, "detail": "PyMuPDF is available"}
    except ImportError:
        checks["pymupdf"] = {"ok": False, "detail": "Install with: pip install pymupdf"}
    checks["vision_configuration"] = {"ok": bool(settings.openai_api_key), "detail": "OPENAI_BASE and OPENAI_API_KEY are configured" if settings.openai_api_key else "OPENAI_API_KEY is missing. Sarvam text models cannot inspect images."}
    checks["openai_base"] = {"ok": bool(settings.openai_base), "detail": settings.openai_base}
    checks["sarvam_text"] = {"ok": bool(settings.sarvam_api_key), "detail": "Sarvam text key is configured" if settings.sarvam_api_key else "SARVAM_API_KEY is missing"}
    if settings.openai_api_key:
        try:
            from PIL import Image, ImageDraw
            test_image = Image.new("RGB", (160, 60), "white")
            ImageDraw.Draw(test_image).text((10, 20), "HELLO", fill="black")
            buffer = io.BytesIO()
            test_image.save(buffer, format="JPEG")
            await _vision_json(buffer.getvalue(), "image/jpeg", Language.EN, "Read the word in this generated test image.")
            checks["vision_live_test"] = {"ok": True, "detail": "Vision provider responded to a generated test image"}
        except HTTPException as error:
            checks["vision_live_test"] = {"ok": False, "detail": str(error.detail)}
        except Exception:
            checks["vision_live_test"] = {"ok": False, "detail": "Vision test failed. Check the backend configuration."}
    else:
        checks["vision_live_test"] = {"ok": False, "detail": "Skipped because OPENAI_API_KEY is missing"}
    return {"checks": checks}


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
            "ocr_lines": ocr_lines, "disclaimers": [DISCLAIMER, "Please show this report to your doctor."], "model": "pdf-text-or-ocr", "model_used": "pdf-text-or-ocr", "ocr_confidence": "low" if any(line["needs_review"] for line in ocr_lines) else "high" if ocr_lines else "not used", "language": language.value,
        }
    else:
        if file_kind == "image/heic":
            raise HTTPException(status_code=415, detail="HEIC needs an installed server-side HEIF decoder. Convert it to JPG or PNG and try again.")
        prepared, mime_type = _prepared_jpeg(content)
        try:
            vision = await _vision_json(prepared, mime_type, language, note)
        except HTTPException as error:
            if error.status_code == 503 and not settings.openai_api_key and not settings.anthropic_api_key:
                guidance = _language_text(
                    language,
                    "Vision analysis is unavailable because OPENAI_API_KEY is not configured. To guide you safely, reply with: is bleeding stopping, how deep and large is the wound, what caused it, and whether there is swelling, pus, fever, or numbness.",
                    "दृश्य विश्लेषण उपलब्ध नहीं है क्योंकि OPENAI_API_KEY सेट नहीं है। सुरक्षित मार्गदर्शन के लिए बताएं: क्या खून रुक रहा है, घाव कितना गहरा और बड़ा है, कैसे लगा, और सूजन, पस, बुखार या सुन्नपन है या नहीं।",
                    "Vision analysis available nahi hai kyunki OPENAI_API_KEY set nahi hai. Safe guidance ke liye batayein: bleeding ruk rahi hai, wound kitna deep aur bada hai, kaise laga, aur swelling, pus, fever ya numbness hai ya nahi.",
                )
                result = {"kind": "guided_wound_questionnaire", "image_quality": "not analysed", "findings": [], "extracted_text": "", "lab_table": [], "first_aid_steps": WOUND_STEPS, "when_to_get_help": WOUND_WARNINGS, "red_flags": [], "care_type": None, "urgency": "review", "reasoning": guidance, "plain_explanation": guidance, "disclaimers": [DISCLAIMER], "model": "vision-unavailable", "model_used": "vision-unavailable", "ocr_confidence": "not used", "language": language.value}
                vision = None
            else:
                raise
        if vision is None:
            pass
        else:
            kind = str(vision.get("kind", "unclear"))
            findings = [str(item) for item in vision.get("findings", [])][:12]
            model_used = settings.openai_vision_model or settings.openai_model if settings.openai_api_key else settings.anthropic_vision_model
            if kind == "xray_or_scan_image":
                explanation = _language_text(language, "Image reading needs a radiologist. Upload the written radiologist report and I can explain its text. If a fracture is suspected, keep the limb still and see a doctor or emergency department.", "इमेज पढ़ने के लिए रेडियोलॉजिस्ट की जरूरत होती है। लिखित रेडियोलॉजिस्ट रिपोर्ट अपलोड करें; मैं उसका टेक्स्ट समझा सकता हूँ। फ्रैक्चर का शक हो तो अंग को स्थिर रखें और डॉक्टर या आपात विभाग जाएं।", "Image reading ke liye radiologist chahiye. Written radiologist report upload karein, main uska text samjha sakta hoon. Fracture ka doubt ho to limb ko still rakhein aur doctor ya emergency department jayein.")
                result = {"kind": kind, "image_quality": str(vision.get("image_quality", "review needed")), "findings": [], "extracted_text": "", "lab_table": [], "first_aid_steps": [], "when_to_get_help": [], "red_flags": [], "care_type": "teleconsultation", "urgency": "scheduled", "reasoning": explanation, "plain_explanation": explanation, "disclaimers": [DISCLAIMER], "model": model_used, "model_used": model_used, "ocr_confidence": "not used", "language": language.value}
            elif kind in {"medical_report", "prescription"}:
                extracted, ocr_lines = _ocr_image(prepared)
                if not extracted:
                    raise HTTPException(status_code=422, detail="OCR could not read the report. Try a brighter, sharper full-page photo.")
                table = _report_table(extracted, ocr_lines) if kind == "medical_report" else []
                explanation = "Values are compared only with the printed ranges in this report. Please show this report to your doctor." if kind == "medical_report" else "This is a transcription to check against the original prescription. Ask the prescribing clinician or pharmacist about any unclear medicine name or instruction; do not change doses from this tool."
                result = {"kind": kind, "image_quality": str(vision.get("image_quality", "review needed")), "findings": [], "extracted_text": extracted[:12000], "lab_table": table, "first_aid_steps": [], "when_to_get_help": [], "red_flags": [], "care_type": "teleconsultation" if table else None, "urgency": "same_day" if any(row["status"] in {"low", "high"} for row in table) else "scheduled", "reasoning": explanation, "plain_explanation": explanation, "questions_for_doctor": ["Which values should I discuss first?", "Do any results need a repeat test?"] if table else [], "ocr_lines": ocr_lines, "disclaimers": [DISCLAIMER, "Please show this report to your doctor."], "model": model_used, "model_used": model_used, "ocr_confidence": "low" if any(line["needs_review"] for line in ocr_lines) else "high", "language": language.value}
            else:
                if kind == "wound_photo":
                    observed = " ".join([str(vision.get("severity", "")), *findings, *[str(item) for item in vision.get("severity_signals", [])]]).lower()
                    if any(flag in observed for flag in ("spurting", "non-stopping", "does not stop", "gaping", "exposed bone", "tendon", "exposed fat", "shock", "deform")):
                        care_type, urgency = "emergency_112", "emergency"
                    elif any(flag in observed for flag in ("moderate", "swelling", "discharge", "pus", "dirty", "deep", "infect")):
                        care_type, urgency = "home_nursing", "same_day"
                    else:
                        care_type, urgency = "gp_teleconsult", "routine"
                else:
                    care_type, urgency = vision.get("care_type"), vision.get("urgency")
                explanation = str(vision.get("plain_explanation", "Please upload a clearer image in good light, with the whole area in frame."))
                result = {"kind": kind, "image_quality": str(vision.get("image_quality", "review needed")), "findings": findings, "extracted_text": "", "lab_table": [], "first_aid_steps": WOUND_STEPS if kind == "wound_photo" else [], "when_to_get_help": WOUND_WARNINGS if kind == "wound_photo" else [], "red_flags": vision.get("severity_signals", []), "care_type": care_type, "urgency": urgency, "reasoning": explanation, "plain_explanation": explanation, "disclaimers": [DISCLAIMER], "model": model_used, "model_used": model_used, "ocr_confidence": "not used", "language": language.value}
    spoken = await _sarvam_audio_reply(str(result["plain_explanation"]), "hi-IN" if language == Language.HI else "en-IN")
    result["audio_base64"] = spoken
    result["audio_mime_type"] = "audio/wav" if spoken else None
    # Metadata only: no file bytes, text, or model response is logged or stored.
    result["processing_ms"] = int((time.monotonic() - started) * 1000)
    logger.info("pathovision type=%s size=%d duration_ms=%d model=%s status=ok", file_kind, len(content), result["processing_ms"], result.get("model_used", result.get("model", "unknown")))
    return result
