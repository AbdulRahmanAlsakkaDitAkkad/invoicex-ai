# invoicex/app/utils.py
from __future__ import annotations
from typing import Dict, Any, List

def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, dict, tuple, set)):
        return len(v) == 0
    return False

def count_missing(d: Dict[str, Any], keys: List[str]) -> int:
    return sum(1 for k in keys if _is_missing(d.get(k)))
