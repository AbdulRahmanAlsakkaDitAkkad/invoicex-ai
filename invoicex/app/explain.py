# invoicex/app/explain.py
from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import numpy as np
import joblib

# lazy caches
_VEC = None
_CLS = None

def _load_artifacts() -> Tuple[Optional[object], Optional[object]]:
    """Load TF-IDF vectorizer and classifier once (if available)."""
    global _VEC, _CLS
    if _VEC is None or _CLS is None:
        try:
            root = Path(__file__).resolve().parents[1] / "models"
            _VEC = joblib.load(root / "vectorizer.joblib")
            _CLS = joblib.load(root / "type_classifier.joblib")
        except Exception:
            _VEC, _CLS = None, None
    return _VEC, _CLS

def _top_token_contributions(text: str, top_k: int = 5) -> List[Dict[str, float]]:
    """
    Compute per-token contributions to the predicted class for a linear model
    (LogisticRegression) with a TF-IDF vectorizer.

    For linear models: contribution ≈ tfidf_value(token) * coef_for_predicted_class(token)
    """
    vec, cls = _load_artifacts()
    if vec is None or cls is None:
        return []

    X = vec.transform([text or ""])              # 1 x V sparse TF-IDF
    # predict class index
    if hasattr(cls, "decision_function"):
        # Choose the class with max decision score
        scores = cls.decision_function(X)        # shape (1, n_classes)
        class_idx = int(np.argmax(scores))
    else:
        class_idx = int(cls.predict(X)[0] == getattr(cls, "classes_", [None])[0])

    # Extract coefficients for the predicted class
    # LogisticRegression.coef_: shape (n_classes, n_features) in multi-class
    coefs = cls.coef_[class_idx]                 # shape (V,)
    # Non-zero columns in the current doc
    X_csr = X.tocsr()
    indices = X_csr.indices
    data = X_csr.data

    # Map feature index -> token string
    try:
        feature_names = np.array(vec.get_feature_names_out())
    except Exception:
        feature_names = None

    contribs: List[Tuple[str, float]] = []
    for idx, tfidf_val in zip(indices, data):
        w = float(coefs[idx]) * float(tfidf_val)
        token = feature_names[idx] if feature_names is not None else f"feat_{idx}"
        contribs.append((token, w))

    # Sort by absolute contribution magnitude, take top_k
    contribs.sort(key=lambda t: abs(t[1]), reverse=True)
    top = contribs[:top_k]

    # Normalize weights to a friendly scale (optional)
    if top:
        max_abs = max(abs(w) for _, w in top) or 1.0
        top = [(tok, float(w / max_abs)) for tok, w in top]

    return [{"token": tok, "weight": w} for tok, w in top]

def explain_for_payload(norm: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prefer model-based explanation (if models are available).
    Fall back to simple token-frequency explanation otherwise.
    """
    text = (norm.get("full_text") or "").lower()

    # Try model-based contributions
    top = _top_token_contributions(text, top_k=5)
    if top:
        return {
            "method": "linear_contribution",
            "details": {"top_tokens": top}
        }

    # Fallback: simple frequency-based tokens (MVP)
    from collections import Counter
    tokens = [t for t in text.split() if len(t) > 2]
    common = Counter(tokens).most_common(3)
    return {
        "method": "feature_importances",
        "details": {"top_tokens": [{"token": t, "weight": float(i)/10.0} for t, i in common]}
    }
