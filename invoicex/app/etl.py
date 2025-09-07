# invoicex/app/etl.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime

# Map Arabic-Indic digits to ASCII (e.g., ١٢٣ -> 123)
ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
ARABIC_INDIC_CHARS = set("٠١٢٣٤٥٦٧٨٩")

def _strip(s: Optional[str]) -> str:
    return str(s or "").strip()

def _ar_digits_to_ascii(s: str) -> str:
    return s.translate(ARABIC_INDIC)

def _normalize_number_str(num: str, lang: str) -> str:
    """
    Convert localized numeric strings into a form Python's float() understands.
    - de: 1.234,56  -> 1234.56
    - ar: ١٬٢٣٤٫٥٦ -> 1234.56 (also converts Arabic digits)
    - en: 1,234.56  -> 1234.56
    """
    s = _strip(num)

    if lang == "ar":
        s = _ar_digits_to_ascii(s)
        s = s.replace("٬", "")  # thousands
        s = s.replace("٫", ".") # decimal
        s = s.replace(",", "")  # safety
        return s

    if lang == "de":
        s = s.replace(".", "")  # thousands
        s = s.replace(",", ".") # decimal
        return s

    # Default EN: remove commas (thousands)
    return s.replace(",", "")

def _to_float(v: Any, lang: str) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = _normalize_number_str(str(v), lang)
    try:
        return float(s)
    except ValueError:
        return None

def _parse_date_localized(date_str: str, lang: str) -> Optional[str]:
    """
    Parse common date formats and return ISO 'YYYY-MM-DD'.
    Examples:
      EN: 2025-07-10, 07/10/2025, 07-10-2025
      DE: 10.07.2025, 10/07/2025, 10-07-2025
      AR: ١٠/٠٧/٢٠٢٥ (converted) -> 10/07/2025, also ISO accepted
    """
    raw = _strip(date_str)
    if not raw:
        return None

    # Always normalize Arabic-Indic digits if present (even if lang != "ar")
    if any(c in ARABIC_INDIC_CHARS for c in raw):
        raw = _ar_digits_to_ascii(raw)

    # Normalize Arabic punctuation if present
    raw = raw.replace("٫", ".").replace("٬", "")

    patterns = {
        "en": ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%d-%m-%Y"],
        "de": ["%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"],
        "ar": ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"],
    }

    for fmt in patterns.get(lang, patterns["en"]):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Extra-tolerant fallbacks (include dotted German format too)
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y", "%d.%m.%Y"]:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None

def normalize(payload: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """
    Normalize all user fields, using 'lang' to correctly parse numbers/dates.
    """
    vendor_name = _strip(payload.get("vendor_name"))
    invoice_number = _strip(payload.get("invoice_number"))
    date_iso = _parse_date_localized(_strip(payload.get("date")), lang)
    tax_id = _strip(payload.get("tax_id"))
    currency = _strip(payload.get("currency") or "EUR").upper()

    # Items + totals
    raw_items = payload.get("items") or []
    items: List[Dict[str, Any]] = []
    total_amount = 0.0

    for it in raw_items:
        desc = _strip(it.get("description"))
        qty = it.get("quantity", 1)
        if isinstance(qty, str) and lang == "ar":
            qty = _ar_digits_to_ascii(qty)
        try:
            qty = int(qty)
        except Exception:
            qty = 1

        unit_price = _to_float(it.get("unit_price", 0.0), lang) or 0.0
        items.append({
            "description": desc,
            "quantity": qty,
            "unit_price": unit_price,
            "category": _strip(it.get("category")),
        })
        total_amount += qty * unit_price

    line_count = len(items)

    # text used by the classifier
    full_text_parts = [
        vendor_name, invoice_number, tax_id, currency,
        *(it["description"] for it in items if it.get("description")),
        _strip(payload.get("raw_text"))
    ]
    if lang == "ar":
        full_text_parts = [_ar_digits_to_ascii(p) for p in full_text_parts]

    return {
        "vendor_name": vendor_name,
        "invoice_number": invoice_number,
        "date": date_iso,                      # ISO or None
        "tax_id": tax_id,
        "items": items,
        "currency": currency,
        "total_amount": round(total_amount, 2) if line_count else None,
        "line_count": line_count,
        "full_text": " ".join([p for p in full_text_parts if p]),
    }
