# invoicex/app/api.py
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schema import InvoiceInput, InvoiceOutput
from .language import detect_language
from .etl import normalize
from .classify import predict_type
from .anomaly import score_anomaly
from .tax import classify_vat
from .explain import explain_for_payload
from . import storage
from .utils import count_missing

app = FastAPI(title="InvoiceX AI", version="0.1.0")

# CORS so you can call the API from anywhere (Swagger, local tools, hosted demos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/upload")
def upload_invoice(inv: InvoiceInput):
    iid = storage.insert_raw(inv.model_dump())
    return {"id": iid}

@app.post("/predict", response_model=InvoiceOutput)
def predict(inv: InvoiceInput):
    try:
        # Raw payload + idempotent insert (or fetch existing)
        payload = inv.model_dump()
        iid, created = storage.insert_raw_or_get(payload)

        # 1) Language → 2) Normalize
        lang = detect_language(payload)
        norm = normalize(payload, lang)

        # 3) Missing/duplicate checks
        missing = count_missing(norm, ["vendor_name", "invoice_number", "date", "tax_id", "currency"])
        is_duplicate = not created

        # 4) Type classification + 5) Anomaly score
        label, conf, _ = predict_type(norm.get("full_text", ""))
        fraud_score, reasons = score_anomaly(norm, is_duplicate, missing)

        # 6) Tax classification (pass language so GCC fallback can trigger)
        tax = classify_vat({**norm, "language": lang})

        # 7) Explainability
        expl = explain_for_payload(norm)

        # 8) Build response
        out = {
            "id": iid,
            "extracted_fields": {
                "vendor_name": norm.get("vendor_name"),
                "invoice_number": norm.get("invoice_number"),
                "date": norm.get("date"),
                "tax_id": norm.get("tax_id"),
                "total_amount": norm.get("total_amount"),
                "currency": norm.get("currency"),
                "line_count": norm.get("line_count"),
            },
            "language": lang,
            "type_class": label,
            "type_confidence": conf,
            "type_explanation": expl,
            "fraud_score": fraud_score,
            "fraud_reasons": reasons,
            "tax_classification": tax,
            "warnings": [],
        }

        if is_duplicate:
            out["warnings"].append(
                "Duplicate (vendor_name, invoice_number) found; review before payment."
            )

        storage.upsert_processed(iid, out)
        return out

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/summary")
def summary():
    return storage.summaries()
