# invoicex/scripts/make_synth.py
from __future__ import annotations
import json, random
from pathlib import Path
from datetime import date, timedelta

VENDORS_EN = ["Northwind Traders", "Acme Corp", "Globex", "Initech"]
VENDORS_DE = ["Muster GmbH", "Beispiel AG", "Belege KG"]
VENDORS_AR = ["شركة المثال", "متاجر الربيع", "شركة الشرق"]

ITEMS = [
    ("Keyboard", "product", 35.0),
    ("Monitor", "product", 150.0),
    ("Cloud support", "service", 120.0),
    ("Consulting", "service", 300.0),
]

CURRENCIES = ["EUR", "EUR", "EUR", "SAR", "AED"]  # skew a bit toward EUR

def rand_date():
    start = date(2024, 1, 1)
    delta = timedelta(days=random.randint(0, 600))
    return (start + delta).isoformat()

def make_record(i: int, lang: str) -> dict:
    if lang == "de":
        vendor = random.choice(VENDORS_DE)
        tax_id = "DE" + "".join(random.choice("0123456789") for _ in range(9))
    elif lang == "ar":
        vendor = random.choice(VENDORS_AR)
        tax_id = random.choice(["SA", "AE", "BH", "OM"]) + "".join(random.choice("0123456789") for _ in range(9))
    else:
        vendor = random.choice(VENDORS_EN)
        tax_id = "FR" + "".join(random.choice("0123456789") for _ in range(9))

    n_lines = random.randint(1, 4)
    items = []
    for _ in range(n_lines):
        desc, cat, unit = random.choice(ITEMS)
        items.append({
            "description": desc,
            "quantity": random.randint(1, 5),
            "unit_price": unit,
            "category": cat
        })

    inv_number = f"{vendor.split()[0][:3].upper()}-{i:05d}"
    cur = random.choice(CURRENCIES)
    return {
        "vendor_name": vendor,
        "invoice_number": inv_number,
        "date": rand_date(),
        "tax_id": tax_id,
        "items": items,
        "currency": cur,
        "language": lang,
        "raw_text": f"{vendor} {inv_number} " + " ".join(x["description"] for x in items)
    }

def make_n(n: int, out_path: Path, langs: list[str]):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for i in range(n):
            lang = random.choice(langs)
            rec = make_record(i, lang)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[OK] wrote {n} records to {out_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--out", type=str, default=str(Path(__file__).resolve().parents[1] / "data" / "synth_invoices.jsonl"))
    parser.add_argument("--langs", nargs="+", default=["en", "de", "ar"])
    args = parser.parse_args()

    make_n(args.n, Path(args.out), args.langs)
