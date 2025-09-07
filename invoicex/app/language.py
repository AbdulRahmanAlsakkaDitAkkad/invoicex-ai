# invoicex/app/language.py
from __future__ import annotations
from typing import Dict, Any
from langdetect import detect, DetectorFactory

# Make detection deterministic (same input -> same result)
DetectorFactory.seed = 0

SUPPORTED = {"en", "de", "ar"}

def _whitelist(code: str) -> str:
    """Return only en/de/ar; anything else falls back to 'en'."""
    code = (code or "").lower()
    return code if code in SUPPORTED else "en"

def detect_language(payload: Dict[str, Any]) -> str:
    """
    1) If 'language' is already in the payload, trust it (but whitelist it).
    2) Else detect from raw_text; if missing, build a tiny text from other fields.
    3) On any error, return 'en' so the pipeline stays stable.
    """
    if payload.get("language"):
        return _whitelist(str(payload["language"]))

    text = payload.get("raw_text") or " ".join([
        str(payload.get("vendor_name") or ""),
        str(payload.get("invoice_number") or ""),
        str(payload.get("currency") or ""),
    ]).strip()

    if not text:
        return "en"

    try:
        return _whitelist(detect(text))
    except Exception:
        return "en"
