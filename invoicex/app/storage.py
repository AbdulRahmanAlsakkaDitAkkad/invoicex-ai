# invoicex/app/storage.py
from __future__ import annotations

import os
import json
import uuid
import datetime as dt
from typing import Dict, Any, Tuple, Optional

from sqlalchemy import (
    create_engine, Column, String, Text, DateTime, UniqueConstraint, select
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import IntegrityError

# Allow hosting to override DB path, default to local SQLite file.
DB_URL = os.getenv("DB_URL", "sqlite:///invoicex.db")

# Engine/session
engine = create_engine(
    DB_URL,
    future=True,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, future=True)
Base = declarative_base()


class InvoiceRow(Base):
    """
    Persist both raw and processed invoice payloads.
    A UNIQUE constraint on (vendor_name, invoice_number) is used for duplicate detection.
    """
    __tablename__ = "invoices"

    id = Column(String, primary_key=True)           # UUID string
    vendor_name = Column(String, nullable=False)
    invoice_number = Column(String, nullable=False)
    raw_json = Column(Text, nullable=False)         # original request payload
    processed_json = Column(Text)                   # pipeline result payload
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("vendor_name", "invoice_number", name="uix_vendor_invoice"),
    )


def init_db() -> None:
    """Create tables if they don't exist."""
    Base.metadata.create_all(engine)


def insert_raw_or_get(data: Dict[str, Any]) -> Tuple[str, bool]:
    """
    Insert a raw invoice row or return the existing one if it already exists.
    Returns: (invoice_id, created_flag)
      created_flag=True  -> new record inserted
      created_flag=False -> duplicate of existing (vendor_name, invoice_number)
    """
    init_db()
    iid = str(uuid.uuid4())
    row = InvoiceRow(
        id=iid,
        vendor_name=(data.get("vendor_name") or ""),
        invoice_number=(data.get("invoice_number") or ""),
        raw_json=json.dumps(data, ensure_ascii=False),
    )
    try:
        with SessionLocal.begin() as s:
            s.add(row)
        return iid, True
    except IntegrityError:
        # UNIQUE constraint hit — fetch the existing row id
        with SessionLocal() as s:
            existing = s.execute(
                select(InvoiceRow.id).where(
                    InvoiceRow.vendor_name == (data.get("vendor_name") or ""),
                    InvoiceRow.invoice_number == (data.get("invoice_number") or ""),
                )
            ).first()
            if existing:
                return existing[0], False
            # In the unlikely case we can't find it, re-raise for visibility
            raise


def insert_raw(data: Dict[str, Any]) -> str:
    """Backwards-compatible simple insert; returns the row id (existing or new)."""
    iid, _ = insert_raw_or_get(data)
    return iid


def upsert_processed(iid: str, processed: Dict[str, Any]) -> None:
    """Attach/overwrite the processed JSON for a given invoice id."""
    init_db()
    with SessionLocal.begin() as s:
        row = s.get(InvoiceRow, iid)
        if row:
            row.processed_json = json.dumps(processed, ensure_ascii=False)


def get_raw(iid: str) -> Optional[Dict[str, Any]]:
    """Fetch raw JSON by id (useful for debugging/tests)."""
    with SessionLocal() as s:
        row = s.get(InvoiceRow, iid)
        if not row:
            return None
        return json.loads(row.raw_json)


def summaries(threshold: float = 0.7) -> Dict[str, Any]:
    """
    Summary for dashboarding/health checks.
    Returns:
      - total
      - anomalies_over_0_7 (backward compatibility key)
      - top_vendors
      - monthly_totals: {YYYY-MM: count}
      - monthly_anomalies_over_threshold: {YYYY-MM: n}
    """
    with SessionLocal() as s:
        rows = s.execute(
            select(InvoiceRow.created_at, InvoiceRow.vendor_name, InvoiceRow.processed_json)
        ).all()

    total = len(rows)
    anomalies = 0
    vendors: Dict[str, int] = {}
    monthly_totals: Dict[str, int] = {}
    monthly_anoms: Dict[str, int] = {}

    for created_at, vendor, pjson in rows:
        vendors[vendor] = vendors.get(vendor, 0) + 1

        month_key = "unknown"
        if isinstance(created_at, dt.datetime):
            month_key = created_at.strftime("%Y-%m")
        monthly_totals[month_key] = monthly_totals.get(month_key, 0) + 1

        if pjson:
            try:
                pj = json.loads(pjson)
                score = float(pj.get("fraud_score") or 0.0)
                if score > threshold:
                    anomalies += 1
                    monthly_anoms[month_key] = monthly_anoms.get(month_key, 0) + 1
            except Exception:
                # ignore broken JSONs silently in summary
                pass

    top_vendors = sorted(vendors.items(), key=lambda kv: kv[1], reverse=True)[:10]

    return {
        "total": total,
        "anomalies_over_0_7": anomalies,
        "top_vendors": top_vendors,
        "monthly_totals": dict(sorted(monthly_totals.items())),
        "monthly_anomalies_over_threshold": dict(sorted(monthly_anoms.items())),
    }
