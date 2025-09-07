from __future__ import annotations
import json
import random
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import IsolationForest
import joblib

# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]  # .../invoicex
DATA_PATH = ROOT / "data" / "synth_invoices.jsonl"
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

RNG = random.Random(42)

# Keywords to help infer labels if we load an external JSONL
MEDICAL_TOKENS = {"clinic", "patient", "procedure", "lab", "icd", "cpt", "insurance", "medical"}
RECUR_TOKENS = {"subscription", "monthly", "auto-renew", "plan", "license", "billing", "cycle", "recurring"}

# -------------------------------------------------------------------
# Data loading / synthesis
# -------------------------------------------------------------------
def _synth_row(label: str, i: int) -> Dict[str, Any]:
    """Create one synthetic invoice row for a given label."""
    if label == "product-based":
        items = [
            {"description": "Keyboard", "quantity": 3, "unit_price": 35.0, "category": "product"},
            {"description": "Monitor",  "quantity": 1, "unit_price": 150.0, "category": "product"},
        ]
        raw_text = "invoice order keyboard monitor unit price quantity SKU shipment"
    elif label == "service-based":
        items = [{"description": "Consulting hours", "quantity": 10, "unit_price": 120.0, "category": "service"}]
        raw_text = "consulting hours rate service fee maintenance retainer monthly"
    elif label == "medical":
        items = [{"description": "Lab test CPT-80053", "quantity": 1, "unit_price": 85.0, "category": "medical"}]
        raw_text = "clinic patient procedure lab test ICD CPT insurance medical"
    else:  # recurring
        items = [{"description": "Monthly license subscription", "quantity": 1, "unit_price": 49.0, "category": "service"}]
        raw_text = "subscription monthly charge auto-renew plan license billing cycle recurring"

    return {
        "vendor_name": f"Vendor {label}",
        "invoice_number": f"{label[:3].upper()}-{i:04d}",
        "date": "2025-07-10",
        "tax_id": "DE12345678",
        "items": items,
        "currency": "EUR",
        "language": "en",
        "raw_text": raw_text,
        "label": label,
    }

def _synthesize_dataset(n_per_class: int = 200) -> pd.DataFrame:
    labels = ["product-based", "service-based", "medical", "recurring"]
    rows: List[Dict[str, Any]] = []
    for lbl in labels:
        for i in range(n_per_class):
            rows.append(_synth_row(lbl, i))
    df = pd.DataFrame(rows)
    return _finalize_df(df)

def _infer_label_from_row(row: Dict[str, Any]) -> str:
    """Best-effort label inference if JSONL doesn't have a label column."""
    # 1) Look for explicit 'label'
    if "label" in row and row["label"]:
        return str(row["label"])

    # 2) Heuristics: tokens in raw_text
    text = " ".join([str(row.get("raw_text") or "")]).lower()
    if any(tok in text for tok in MEDICAL_TOKENS):
        return "medical"
    if any(tok in text for tok in RECUR_TOKENS):
        return "recurring"

    # 3) Heuristics: item categories
    items = row.get("items") or []
    if items and all((it.get("category") or "") == "service" for it in items):
        return "service-based"

    # default
    return "product-based"

def _finalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Build helper columns used by models."""
    # full_text = vendor, invoice id, item descriptions, raw_text (if present)
    def join_text(r):
        desc = " ".join([str(it.get("description") or "") for it in (r.get("items") or [])])
        return " ".join([str(r.get("vendor_name") or ""),
                         str(r.get("invoice_number") or ""),
                         desc,
                         str(r.get("raw_text") or "")]).strip()

    df = df.copy()
    df["full_text"] = df.apply(join_text, axis=1)
    df["total_amount"] = df["items"].apply(lambda items: sum((it.get("quantity", 0) * it.get("unit_price", 0.0)) for it in items))
    df["line_count"] = df["items"].apply(lambda items: len(items or []))
    return df

def load_data() -> pd.DataFrame:
    """
    Load JSONL if available; otherwise synthesize a balanced dataset.
    Ensures df has columns: label, full_text, total_amount, line_count.
    """
    if DATA_PATH.exists():
        rows: List[Dict[str, Any]] = []
        with DATA_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                # inject label if missing
                if "label" not in row or not row["label"]:
                    row["label"] = _infer_label_from_row(row)
                rows.append(row)
        df = pd.DataFrame(rows)
        if "label" not in df.columns:
            df["label"] = df.apply(lambda r: _infer_label_from_row(r.to_dict()), axis=1)
        return _finalize_df(df)

    # No file? Build synthetic data with 4 labels.
    return _synthesize_dataset(n_per_class=200)

# -------------------------------------------------------------------
# Training
# -------------------------------------------------------------------
def train_classifier(df: pd.DataFrame) -> None:
    vec = TfidfVectorizer(min_df=1, max_features=5000, ngram_range=(1, 2))
    X = vec.fit_transform(df["full_text"])
    y = df["label"]

    clf = LogisticRegression(max_iter=300, multi_class="auto", solver="lbfgs")
    clf.fit(X, y)

    joblib.dump(vec, MODEL_DIR / "vectorizer.joblib")
    joblib.dump(clf, MODEL_DIR / "type_classifier.joblib")
    print("[OK] Saved classifier + vectorizer -> models/vectorizer.joblib, models/type_classifier.joblib")

def train_iforest(df: pd.DataFrame) -> None:
    X = df[["total_amount", "line_count"]].values
    iforest = IsolationForest(n_estimators=200, contamination=0.05, random_state=0)
    iforest.fit(X)
    joblib.dump(iforest, MODEL_DIR / "anomaly_iforest.joblib")
    print("[OK] Saved anomaly IsolationForest -> models/anomaly_iforest.joblib")

# -------------------------------------------------------------------
def main():
    df = load_data()
    print(f"Training on {len(df)} rows with labels:", dict(df["label"].value_counts()))
    train_classifier(df)
    train_iforest(df)

if __name__ == "__main__":
    main()
