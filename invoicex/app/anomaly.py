# invoicex/app/anomaly.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple, List
import numpy as np
import joblib

# Path to the trained IsolationForest model
ROOT = Path(__file__).resolve().parents[1]
IFOREST_PATH = ROOT / "models" / "anomaly_iforest.joblib"

# Load the model once
_IFOREST = joblib.load(IFOREST_PATH)

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def _safe_int(x, default=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        return default

def score_anomaly(norm: Dict, is_duplicate: bool, missing_count: int) -> Tuple[float, List[str]]:
    """
    Compute a fraud/anomaly risk score and reasons.

    IMPORTANT: The IsolationForest was trained on EXACTLY TWO FEATURES:
      [total_amount, line_count]
    So we must pass the same two features here, in that order.
    Then we add small rule-based bumps for duplicates and missing fields.
    """
    amt = _safe_float(norm.get("total_amount"))
    lc = _safe_int(norm.get("line_count"))

    # >>> EXACTLY TWO FEATURES, same as training <<<
    X = np.array([[amt, lc]], dtype=float)

    # IsolationForest.decision_function: higher = more normal
    raw = float(_IFOREST.decision_function(X)[0])

    # Convert to a 0..1 "risk" where higher = riskier
    # (Invert and clip — simple but effective for an MVP)
    base_risk = float(np.clip(0.5 - raw, 0.0, 1.0))

    risk = base_risk
    reasons: List[str] = []

    if is_duplicate:
        risk += 0.25
        reasons.append("Possible duplicate invoice (same vendor+number).")

    if missing_count > 0:
        risk += 0.10 * min(missing_count, 5)
        reasons.append(f"{missing_count} critical fields missing.")

    # Keep within [0, 0.99] to avoid edge cases
    risk = float(np.clip(risk, 0.0, 0.99))

    if risk < 0.15 and not reasons:
        reasons.append("Looks consistent with past invoices.")

    return risk, reasons
