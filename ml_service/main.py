"""Single, optional FastAPI service for skin and prescription image inference."""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps, UnidentifiedImageError
from torchvision import transforms

from ml.rx.models import load_model as load_rx_model
from ml.rx.model import CRNN as RxCRNN
from ml.rx.charset import load_charset
from ml.rx.decode import best_path, lexicon_correct
from ml.rx.transforms import preprocess_word
from ml.skin.data import CLASS_NAMES
from ml.rx.segment import propose_boxes
from ml.skin.models import load_model as load_skin_model
from ml.common.gradcam import overlay_png

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "ml" / "artifacts"
MAX_BYTES = 10 * 1024 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP"}
app = FastAPI(title="Niramaya ML Inference", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000,http://127.0.0.1:3000").split(","), allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["*"])
_cache: dict[str, tuple[torch.nn.Module, dict[str, Any]]] = {}
SKIN_NAMES = {"akiec":"Actinic keratoses / intraepithelial carcinoma", "bcc":"Basal cell carcinoma", "bkl":"Benign keratosis-like lesion", "df":"Dermatofibroma", "mel":"Melanoma", "nv":"Melanocytic nevus", "vasc":"Vascular lesion"}
CONDITION_CARDS = json.loads((ROOT / "ml" / "skin" / "conditions.json").read_text(encoding="utf-8"))


def _artifact(task: str):
    folder = ARTIFACTS / task
    weights, meta_path = folder / "model.pt", folder / "model_meta.json"
    if not weights.is_file() or not meta_path.is_file():
        return None
    if task not in _cache:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if task == "skin": model = load_skin_model(meta.get("model_type", "custom"), int(meta["num_classes"]))
        elif meta.get("model_type") == "crnn_ctc": model = RxCRNN(int(meta["num_characters"]), int(meta.get("input_height", 32)), int(meta.get("input_width", 128)))
        else: model = load_rx_model(meta.get("model_type", "custom"), int(meta["num_classes"]))
        checkpoint = torch.load(weights, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint.get("model_state", checkpoint.get("state_dict", checkpoint)))
        model.eval()
        _cache[task] = (model, meta)
    return _cache[task]


async def _image(file: UploadFile) -> Image.Image:
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: raise HTTPException(413, "Choose an image smaller than 10 MB.")
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in ALLOWED_FORMATS: raise HTTPException(415, "Use a JPEG, PNG, WEBP, or BMP image.")
        image.load()
        return ImageOps.exif_transpose(image).convert("RGB")
    except UnidentifiedImageError as error:
        raise HTTPException(400, "The uploaded file is not a supported image.") from error


def _tensor(image: Image.Image, meta: dict[str, Any], size: int, grayscale=False):
    if grayscale:
        image = image.convert("L").resize((size[1], size[0]), Image.Resampling.BILINEAR)
        arr = np.asarray(image).astype(np.float32) / 255.0
        if meta.get("binarize"): arr = (arr > float(meta.get("binarize_threshold", 0.65))).astype(np.float32)
        mean, std = float(meta.get("mean", [0.5])[0]), float(meta.get("std", [0.5])[0])
        arr = (arr - mean) / max(std, 1e-6)
        return torch.from_numpy(arr.copy())[None, None]
    transform = transforms.Compose([transforms.Resize(size), transforms.CenterCrop(size), transforms.ToTensor(), transforms.Normalize(meta.get("mean", [0.5]*3), meta.get("std", [0.5]*3))])
    return transform(image).unsqueeze(0)


def _cam(model, tensor, class_index, task, meta):
    # Exported model type determines a stable convolutional target layer.
    names = dict(model.named_modules())
    if task == "skin": target = "backbone.features.7" if "backbone.features.7" in names else "features.6"
    else: target = "backbone.layer4.1.conv2" if "backbone.layer4.1.conv2" in names else "block4.0.3"
    try:
        raw = overlay_png(model, tensor, class_index, target)
        return base64.b64encode(raw).decode("ascii")
    except Exception:
        return None


@app.get("/health")
def health():
    models = {}
    for name in ("skin", "rx"):
        try:
            models[name] = "loaded" if _artifact(name) is not None else "missing"
        except Exception:
            models[name] = "error"
    return {"status": "ok", "models": {"derma": models["skin"], "rx": models["rx"]}, "skin_model": models["skin"] == "loaded", "rx_model": models["rx"] == "loaded"}


@app.get("/derma/info")
@app.get("/skin/info")
def derma_info():
    try:
        loaded = _artifact("skin")
    except Exception:
        loaded = None
    meta = loaded[1] if loaded else {}
    return {
        "status": "ok" if loaded else "model_missing",
        "classes": [{"code": code, "name": CONDITION_CARDS.get(code, {}).get("name", CLASS_NAMES.get(code, code))} for code in meta.get("class_codes", meta.get("class_names", list(CLASS_NAMES)))],
        "model_type": meta.get("model_type"),
        "metrics": meta.get("metrics"),
        "condition_cards": CONDITION_CARDS,
        "disclaimer": "Educational screening aid for HAM10000-like dermatoscopic images only. It is not a diagnosis and is not validated for every skin or medical image.",
    }


@app.get("/rx/info")
def rx_info():
    try: model = _artifact("rx")
    except Exception: model = None
    path = ARTIFACTS / "rx" / "medicines.json"
    medicines = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    lexicon_path = ARTIFACTS / "rx" / "lexicon.json"
    lexicon = json.loads(lexicon_path.read_text(encoding="utf-8")) if lexicon_path.exists() else []
    meta = model[1] if model else {}
    return {"status": "ok" if model else "model_missing", "model_type": meta.get("model_type"), "metrics": meta.get("metrics"), "count": len(medicines), "lexicon_size": len(lexicon) or len(medicines), "medicines": medicines, "disclaimer": "Medicine names are unverified candidates. Confirm each name with a pharmacist; this model does not read dose or instructions."}


@app.post("/skin/predict")
@app.post("/derma/predict")
async def skin_predict(image: UploadFile = File(...)):
    loaded = _artifact("skin")
    if not loaded: return {"status": "model_missing", "message": "No trained skin model is installed. You can continue with symptom-based care guidance."}
    model, meta = loaded
    source = await _image(image)
    tensor = _tensor(source, meta, int(meta.get("input_size", 224)))
    with torch.no_grad(): probs = model(tensor).softmax(dim=1)[0]
    values, indexes = probs.topk(min(3, len(probs)))
    codes = meta.get("class_codes", meta.get("class_names", list(SKIN_NAMES)))
    classes = meta.get("class_names", {})
    top = [{"code": codes[int(i)], "name": classes.get(codes[int(i)], SKIN_NAMES.get(codes[int(i)], codes[int(i)])), "confidence": float(v)} for v, i in zip(values, indexes)]
    high_codes = set(meta.get("risk_mapping", {}).get("high_risk_classes", ["mel", "bcc", "akiec"]))
    high_sum = sum(float(probs[i]) for i, code in enumerate(codes) if code in high_codes)
    max_conf = top[0]["confidence"]
    thresholds = meta.get("confidence_thresholds", {})
    if any(p["code"] in high_codes for p in top[:1]) and max_conf >= float(thresholds.get("high_risk_confidence", .5)) or high_sum >= float(thresholds.get("high_risk_sum", .4)):
        risk, effect = "needs_clinician_review", "raise_priority"
    elif max_conf < float(thresholds.get("uncertain_confidence", .4)):
        risk, effect = "uncertain", "retake_photo"
    else: risk, effect = "lower_risk_pattern", "no_change"
    card = CONDITION_CARDS.get(top[0]["code"], {})
    message = "Please arrange clinician review soon." if effect == "raise_priority" else "The image is unclear; retake it in even light and seek clinical review if concerned." if effect == "retake_photo" else "This pattern does not rule out disease; continue normal care and consult a clinician if it changes or worries you."
    disclaimer = "Information only, not medical advice or a diagnosis. HAM10000 covers dermatoscopic lesion classes; it cannot classify every skin or medical image."
    return {"status": "ok", "risk": risk, "risk_level": risk, "triage_effect": effect, "top_prediction": top[0], "top_predictions": top, "top3": top, "high_risk_probability": high_sum, "condition_card": card, "message": message, "gradcam_png_base64": _cam(model, tensor, int(indexes[0]), "skin", meta), "model_version": meta.get("training_date", "unknown"), "disclaimer": disclaimer}


@app.post("/rx/segment")
async def rx_segment(image: UploadFile = File(...)):
    source = await _image(image)
    boxes = propose_boxes(source, max_boxes=30)
    return {"status": "ok", "boxes": boxes, "image_width": source.width, "image_height": source.height, "message": "Review and adjust the proposed word crops before reading them." if boxes else "No word regions were found. Add medicine-name boxes manually."}


@app.post("/rx/predict")
async def rx_predict(image: UploadFile | None = File(default=None), crops: list[UploadFile] | None = File(default=None), boxes: str | None = Form(default=None)):
    loaded = _artifact("rx")
    if not loaded: return {"status": "model_missing", "message": "No trained prescription model is installed. You can enter medicine names manually."}
    model, meta = loaded
    sources = []
    if image is not None:
        source = await _image(image)
        try: requested = json.loads(boxes or "[]")
        except json.JSONDecodeError as error: raise HTTPException(400, "Crop boxes are invalid.") from error
        for box in requested[:20]:
            x, y, w, h = (int(box[k]) for k in ("x", "y", "w", "h"))
            x0, y0, x1, y1 = max(0,x), max(0,y), min(source.width,x+w), min(source.height,y+h)
            if x1 <= x0 or y1 <= y0: continue
            sources.append(source.crop((x0,y0,x1,y1)))
    for crop in crops or []:
        if len(sources) >= 20: break
        sources.append(await _image(crop))
    if not sources: raise HTTPException(400, "Add one or more medicine-name crops first.")
    height, width = meta.get("input_size", [64, 256])
    medicines_path = ARTIFACTS / "rx" / "medicines.json"
    medicines = json.loads(medicines_path.read_text(encoding="utf-8")) if medicines_path.exists() else {}
    results = []
    for crop in sources:
        if meta.get("model_type") == "crnn_ctc":
            charset_path = ARTIFACTS / "rx" / "charset.json"
            lexicon_path = ARTIFACTS / "rx" / "lexicon.json"
            if not charset_path.is_file(): raise HTTPException(503, "RxRead character set is missing from the exported model.")
            charset = load_charset(charset_path)
            lexicon = json.loads(lexicon_path.read_text(encoding="utf-8")) if lexicon_path.is_file() else []
            tensor = preprocess_word(crop, int(meta.get("input_height", 32)), int(meta.get("input_width", 128)), float(meta.get("mean", 0.5)), float(meta.get("std", 0.25))).unsqueeze(0)
            with torch.no_grad(): log_probs = model(tensor)[:, 0]
            raw_text, ctc_confidence = best_path(log_probs, charset)
            candidates = lexicon_correct(raw_text, lexicon, k=3)
            top = []
            for candidate in candidates:
                final_score = ctc_confidence * (float(candidate["score"]) / 100.0)
                top.append({"brand": candidate["name"], "generic": candidate.get("composition", ""), "confidence": ctc_confidence, "lexicon_score": candidate["score"], "final_score": final_score})
            results.append({"raw_text": raw_text, "top_predictions": top, "confidence": ctc_confidence, "needs_manual_entry": not candidates or float(candidates[0]["score"]) < 70, "gradcam_png_base64": None})
            continue
        # preprocess_word provides the exact train-time grayscale/threshold/pad convention.
        word = ImageOps.autocontrast(crop.convert("L"))
        if meta.get("binarize"): word = word.point(lambda value: 255 if value > 160 else 0)
        ratio = int(height) / max(1, word.height)
        resized_width = max(1, min(int(width), round(word.width * ratio)))
        word = word.resize((resized_width, int(height)), Image.Resampling.LANCZOS)
        canvas = Image.new("L", (int(width), int(height)), 255); canvas.paste(word, (0, 0))
        arr = np.asarray(canvas).astype(np.float32) / 255.0
        arr = (arr - float(meta.get("mean", .5))) / max(float(meta.get("std", .25)), 1e-5)
        tensor = torch.from_numpy(arr.copy())[None, None]
        with torch.no_grad(): probs = model(tensor).softmax(dim=1)[0]
        values, indexes = probs.topk(min(3, len(probs)))
        top = []
        for value, index in zip(values, indexes):
            medicine = medicines.get(str(int(index)), {})
            top.append({"brand": medicine.get("brand", meta.get("class_names", [])[int(index)]), "generic": medicine.get("generic", ""), "confidence": float(value)})
        results.append({"top_predictions": top, "confidence": top[0]["confidence"], "gradcam_png_base64": _cam(model, tensor, int(indexes[0]), "rx", meta)})
    return {"status": "ok", "results": results, "disclaimer": "Candidates can be wrong. Confirm or correct every name; this feature does not read dosage or instructions."}
