# invoicex/app/tax.py
from __future__ import annotations
from typing import Dict, Any, Tuple
import re

# --- Demo standard VAT rate tables (subset for MVP) ---

EU_STANDARD = {
    "DE": 0.19, "FR": 0.20, "IT": 0.22, "ES": 0.21, "NL": 0.21, "BE": 0.21,
    "AT": 0.20, "PT": 0.23, "SE": 0.25, "DK": 0.25, "FI": 0.25, "IE": 0.23,
}

# GCC (subset; ISO Alpha-2)
GCC_STANDARD = {
    "AE": 0.05,  # United Arab Emirates
    "SA": 0.15,  # Saudi Arabia (current standard rate)
    "BH": 0.10,  # Bahrain
    "OM": 0.05,  # Oman
    # QA / KW omitted in this MVP
}

# Currency → GCC country hint (best effort when tax_id lacks a country prefix)
CURRENCY_TO_GCC = {
    "AED": "AE",
    "SAR": "SA",
    "BHD": "BH",
    "OMR": "OM",
}

# --- Explicit textual cues ----------------------------------------------
# Exemption (EU/GCC): reverse charge / Article 196 / explicit "VAT exempt"
_EXEMPT_PATTERNS = [
    r"\breverse\s*charge\b",
    r"\barticle\s*196\b",
    r"\bvat[-\s]*exempt\b",
]

# Zero-rated: explicit "zero-rated" / "0% VAT" or clear export/international transport cue
_ZERO_RATED_PATTERNS = [
    r"\bzero[-\s]*rated\b",
    r"\bvat\s*0%|\b0%\s*vat\b",
    r"\bexport\b.*\b(outside|to)\s*(eu|gcc)\b",
    r"\binternational\s*transport(ation)?\b",
]

EXEMPT_PATTERNS = [re.compile(p, re.I) for p in _EXEMPT_PATTERNS]
ZERO_RATED_PATTERNS = [re.compile(p, re.I) for p in _ZERO_RATED_PATTERNS]


def _decide_region_and_rate(norm: Dict[str, Any]) -> Tuple[str, float, str]:
    """
    Decide region and base standard rate (before checking explicit exemptions/zero-rating).
    Returns (region, rate, country_code_hint)
    """
    tax_id = (norm.get("tax_id") or "").upper()
    cur = (norm.get("currency") or "").upper()
    language = (norm.get("language") or "").lower()

    cc = tax_id[:2]

    # EU by VAT ID prefix
    if cc in EU_STANDARD:
        return "EU", EU_STANDARD[cc], cc

    # GCC by VAT ID prefix
    if cc in GCC_STANDARD:
        return "GCC", GCC_STANDARD[cc], cc

    # GCC by currency hint
    if cur in CURRENCY_TO_GCC:
        gcc_cc = CURRENCY_TO_GCC[cur]
        return "GCC", GCC_STANDARD.get(gcc_cc, 0.15), gcc_cc

    # Language fallback: Arabic -> GCC default (best-effort)
    if language == "ar":
        return "GCC", 0.15, "GCC"

    # Default fallback
    return "Unknown", 0.15, ""


def classify_vat(norm: Dict[str, Any]) -> Dict[str, Any]:
    """
    MVP rule-based VAT classification aligned with EU/GCC norms:
      - Default to standard rate per jurisdiction.
      - Only set EXEMPT or ZERO-RATED if explicit text cues are present.
      - Provide an explanation 'reason' for transparency.
    """
    # 1) Decide region & base standard rate
    region, standard_rate, cc_hint = _decide_region_and_rate(norm)

    # 2) Look for explicit exemptions (override to 0%)
    text = f"{(norm.get('raw_text') or '')} {(norm.get('full_text') or '')}"
    for pat in EXEMPT_PATTERNS:
        m = pat.search(text)
        if m:
            return {
                "region": region,
                "vat": "exempt",
                "rate": 0.0,
                "reason": f"Detected exemption keyword (“{m.group(0)}”).",
            }

    # 3) Look for explicit zero-rating cues (override to 0%)
    for pat in ZERO_RATED_PATTERNS:
        m = pat.search(text)
        if m:
            return {
                "region": region if region != "Unknown" else "Unknown",
                "vat": "zero-rated",
                "rate": 0.0,
                "reason": f"Detected zero-rated cue (“{m.group(0)}”).",
            }

    # 4) Apply standard rate for the decided region
    if region == "EU" and cc_hint in EU_STANDARD:
        return {
            "region": "EU",
            "vat": "standard",
            "rate": EU_STANDARD[cc_hint],
            "reason": f"EU VAT ID prefix {cc_hint} → apply country standard rate (demo table).",
        }

    if region == "GCC":
        rate = GCC_STANDARD.get(cc_hint, standard_rate)
        hint = cc_hint if cc_hint in GCC_STANDARD else "GCC"
        return {
            "region": "GCC",
            "vat": "standard",
            "rate": rate,
            "reason": f"{'GCC VAT ID' if cc_hint in GCC_STANDARD else 'GCC inference'} ({hint}) → apply standard rate (demo table).",
        }

    # 5) Unknown region: generic standard
    return {
        "region": "Unknown",
        "vat": "standard",
        "rate": standard_rate,
        "reason": "Default standard rate for MVP; verify jurisdiction/rules.",
    }
