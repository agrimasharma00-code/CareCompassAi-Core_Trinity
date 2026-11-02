import base64, io, json, os
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DERMA_DISCLAIMER = "AI-assisted triage aid, not a diagnosis. A doctor must review."
RX_DISCLAIMER = "AI suggestions may be wrong. Always confirm with the prescription or a pharmacist."


def _allow_synthetic():
    """Developer-only switch: set ALLOW_SYNTHETIC_MODELS=1 to load fake-data models for local testing."""
    return os.getenv("ALLOW_SYNTHETIC_MODELS") == "1"


class Models:
    """Loads the DermaScan and RxRead models once at startup, independently of each other."""

    def __init__(self):
        self.derma = "missing"
        self.rx = "missing"
        self.derma_model = None
        self.rx_model = None
        self.derma_meta = {}
        self.rx_meta = {}
        self.lexicon = []
        self.charset = []
        self.torch = None
        self.cards = json.loads((ROOT / "ml/derma/conditions.json").read_text(encoding="utf-8"))
        self._load()

    def _load(self):
        try:
            import torch
        except ImportError:
            return
        self.torch = torch
                # ML_ARTIFACTS_DIR lets tests (or deployments) point to a different models folder
        base = Path(os.getenv("ML_ARTIFACTS_DIR") or (ROOT / "ml/artifacts"))
        self._load_derma(base / "derma")
        self._load_rx(base / "rx")

    def _load_derma(self, d):
        try:
            if not ((d / "model.pt").exists() and (d / "model_meta.json").exists()):
                return  # stays "missing"
            self.derma_meta = json.loads((d / "model_meta.json").read_text())

            # Refuse synthetic (fake-data) models unless the developer switch is on
            is_trained = self.derma_meta.get("trained", not self.derma_meta.get("synthetic", False))
            if not is_trained and not _allow_synthetic():
                raise ValueError("Synthetic-only DermaScan model is not enabled for inference "
                                 "(set ALLOW_SYNTHETIC_MODELS=1 for local testing)")

            from ml.derma.models import build_model
            self.derma_model = build_model(self.derma_meta.get("architecture", "custom"), pretrained=False)
            checkpoint = self.torch.load(d / "model.pt", map_location="cpu", weights_only=False)
            self.derma_model.load_state_dict(checkpoint.get("state_dict", checkpoint))
            self.derma_model.eval()
            self.derma = "loaded"
            print(f"[ml_service] DermaScan loaded (synthetic={self.derma_meta.get('synthetic', False)})")
        except Exception:
            traceback.print_exc()
            self.derma = "error"
            self.derma_model = None

    def _load_rx(self, r):
        try:
            if not ((r / "model.pt").exists() and (r / "model_meta.json").exists()):
                return  # stays "missing"
            self.rx_meta = json.loads((r / "model_meta.json").read_text())

            # Refuse untrained models unless the developer switch is on
            if not self.rx_meta.get("trained", False) and not _allow_synthetic():
                raise ValueError("RxRead model is not marked as trained "
                                 "(set ALLOW_SYNTHETIC_MODELS=1 for local testing)")

            from ml.rx.model import build_model
            self.charset = json.loads((r / "charset.json").read_text())
            self.lexicon = json.loads((r / "lexicon.json").read_text())
            self.rx_model = build_model(len(self.charset),
                                        self.rx_meta.get("height", 32),
                                        self.rx_meta.get("width", 128))
            checkpoint = self.torch.load(r / "model.pt", map_location="cpu", weights_only=False)
            self.rx_model.load_state_dict(checkpoint.get("state_dict", checkpoint))
            self.rx_model.eval()
            self.rx = "loaded"
            print(f"[ml_service] RxRead loaded (trained={self.rx_meta.get('trained', False)})")
        except Exception:
            traceback.print_exc()
            self.rx = "error"
            self.rx_model = None

def validate_image(contents, filename="upload.jpg"):
    from fastapi import HTTPException
    from PIL import Image,ImageOps,UnidentifiedImageError
    suffix=Path(filename or "upload.jpg").suffix.lower()
    if suffix not in {".jpg",".jpeg",".png",".webp",".heic",".heif"}: raise HTTPException(415,"Supported formats: JPG, PNG, WebP; HEIC requires pillow-heif.")
    if len(contents)>10*1024*1024: raise HTTPException(413,"Image exceeds 10 MB.")
    try:
        if suffix in {".heic",".heif"}:
            try: import pillow_heif; pillow_heif.register_heif_opener()
            except ImportError: raise HTTPException(415,"HEIC support is unavailable. Upload JPG, PNG, or WebP.")
        image=ImageOps.exif_transpose(Image.open(io.BytesIO(contents))).convert("RGB")
        image.load(); return image
    except HTTPException: raise
    except (UnidentifiedImageError,OSError,ValueError): raise HTTPException(400,"The uploaded image is unreadable or corrupt.")

def derma_info(models):
    return {"classes":list(("akiec","bcc","bkl","df","mel","nv","vasc")),"condition_cards":models.cards,"model_type":models.derma_meta.get("architecture"),"metrics_summary":None,"disclaimer":DERMA_DISCLAIMER}

def predict_derma(models,image):
    if models.derma!="loaded":
        from fastapi import HTTPException
        raise HTTPException(503,{"status":"model_missing","message":"DermaScan model not trained yet. Run `python -m ml.derma.train --model custom --quick --data-dir ml/data/ham10000` and `python -m ml.derma.export`."})
    from ml.derma.config import CLASSES,risk_from_probabilities
    from ml.derma.transforms import preprocess_eval
    size=int(models.derma_meta.get("input_size",224)); x=preprocess_eval(image,size).unsqueeze(0); model=models.derma_model
    with models.torch.no_grad(): probs=model(x).softmax(1)[0].cpu().tolist()
    order=sorted(range(len(probs)),key=lambda i:probs[i],reverse=True); top=order[0]; decision=risk_from_probabilities(probs,CLASSES)
    top_prediction={"code":CLASSES[top],"name":models.cards[CLASSES[top]]["name"],"confidence":float(probs[top])}
    top3=[{"code":CLASSES[i],"name":models.cards[CLASSES[i]]["name"],"confidence":float(probs[i])} for i in order[:3]]
    cam_data=None
    try:
        import numpy as np
        from PIL import Image as PILImage
        from ml.common.gradcam import gradcam
        layer=next(module for module in reversed(list(model.modules())) if isinstance(module,models.torch.nn.Conv2d))
        cam=gradcam(model,x,layer); heat=np.zeros((*cam.shape,3),dtype=np.uint8);heat[...,0]=(cam*255).astype(np.uint8);heat[...,1]=(np.maximum(cam-.25,0)*150).astype(np.uint8)
        base=np.asarray(image.resize((size,size)),dtype=np.float32);overlay=(base*.58+heat*.42).clip(0,255).astype(np.uint8);buffer=io.BytesIO();PILImage.fromarray(overlay).save(buffer,format="PNG");cam_data=base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception: cam_data=None
    return {"status":"ok","top_prediction":top_prediction,"top3":top3,**decision,"condition_card":models.cards[CLASSES[top]],"message":"This result is an educational image-classifier output; arrange clinician review as appropriate.","gradcam_png_base64":cam_data,"model_version":str(models.derma_meta.get("version","unversioned")),"disclaimer":DERMA_DISCLAIMER}

def rx_info(models): return {"model_type":models.rx_meta.get("architecture"),"metrics_summary":None,"lexicon_size":len(models.lexicon),"disclaimer":RX_DISCLAIMER}

def predict_rx(models, image, boxes):
    if models.rx!="loaded":
        from fastapi import HTTPException
        raise HTTPException(503,{"status":"model_missing","message":"RxRead model not trained yet. Run `python -m ml.rx.train --stage bd_only --quick --synthetic` and `python -m ml.rx.export`."})
    from ml.rx.transforms import preprocess
    from ml.rx.decode import best_path,beam_search
    import numpy as np
    height,width=int(models.rx_meta.get("height",32)),int(models.rx_meta.get("width",128));results=[]
    for box in boxes[:20]:
        try: x,y,w,h=(int(box[k]) for k in ("x","y","w","h"))
        except (KeyError,TypeError,ValueError): results.append({"box":box,"status":"invalid_box"});continue
        x0=max(0,min(image.width,x));y0=max(0,min(image.height,y));x1=max(0,min(image.width,x+w));y1=max(0,min(image.height,y+h))
        clipped={"x":x0,"y":y0,"w":x1-x0,"h":y1-y0}
        if clipped["w"]<=0 or clipped["h"]<=0: results.append({"box":clipped,"status":"invalid_box"});continue
        arr=preprocess(image.crop((x0,y0,x1,y1)),height,width); tensor=models.torch.tensor(arr).unsqueeze(0).unsqueeze(0)
        with models.torch.no_grad(): logits=models.rx_model(tensor).exp().squeeze(1).cpu().numpy()
        raw=best_path(logits,models.charset); beam=beam_search(np.log(np.maximum(logits,1e-9)),models.charset)
        candidates=__import__("ml.rx.lexicon",fromlist=["lexicon_correct"]).lexicon_correct(beam,models.lexicon,3)
        confidence=float(logits.max(axis=1).mean()); bestscore=candidates[0]["score"] if candidates else 0
        results.append({"box":clipped,"raw_text":raw,"beam_text":beam,"ctc_confidence":confidence,"candidates":candidates,"confidence_level":"high" if confidence>=.8 else "medium" if confidence>=.55 else "low","needs_manual_entry":bestscore<70,"status":"ok"})
    return {"status":"ok","results":results,"model_version":str(models.rx_meta.get("version","unversioned")),"disclaimer":RX_DISCLAIMER}
