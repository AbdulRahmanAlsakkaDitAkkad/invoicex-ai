# invoicex/app/classify.py
from __future__ import annotations
from typing import Tuple, Dict, Optional
from pathlib import Path
import joblib

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
VEC_PATH = MODEL_DIR / "vectorizer.joblib"
CLS_PATH = MODEL_DIR / "type_classifier.joblib"

_VEC = None  # lazy cache
_CLS = None  # lazy cache

def _load_models() -> Tuple[Optional[object], Optional[object]]:
    global _VEC, _CLS
    if _VEC is None or _CLS is None:
        try:
            _VEC = joblib.load(VEC_PATH)
            _CLS = joblib.load(CLS_PATH)
        except Exception:
            _VEC, _CLS = None, None
    return _VEC, _CLS

def predict_type(text: str) -> Tuple[str, float, Dict[str, float]]:
    vec, cls = _load_models()
    if vec is not None and cls is not None:
        X = vec.transform([text or ""])
        if hasattr(cls, "predict_proba"):
            probs = cls.predict_proba(X)[0]
            classes = list(cls.classes_)
            by_class = {c: float(p) for c, p in zip(classes, probs)}
            best_idx = int(probs.argmax())
            return classes[best_idx], float(probs[best_idx]), by_class
        # fallback if classifier has no proba
        label = cls.predict(X)[0]
        return str(label), 1.0, {str(label): 1.0}

    # Heuristic fallback if models not available
    t = (text or "").lower()
    if any(w in t for w in ["monitor", "keyboard", "product", "item", "pcs"]):
        return "product-based", 0.7, {"product-based": 0.7}
    if any(w in t for w in ["hours", "service", "consult", "maintenance", "support", "subscription"]):
        return "service-based", 0.7, {"service-based": 0.7}
    return "other", 0.5, {"other": 0.5}
