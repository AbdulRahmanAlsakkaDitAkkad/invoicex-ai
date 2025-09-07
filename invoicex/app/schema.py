# invoicex/app/schema.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator, ConfigDict

class InvoiceItem(BaseModel):
    description: str
    # Allow localized strings OR numbers. ETL will parse/normalize.
    quantity: Union[int, str] = 1
    unit_price: Union[float, str] = 0.0
    category: Optional[str] = None

    model_config = ConfigDict(extra="ignore")  # ignore unknown keys

    @field_validator("quantity")
    @classmethod
    def _quantity_ok(cls, v):
        """
        - If it's a string (e.g., '١', '2'), keep it as-is; ETL normalizes later.
        - If it's numeric, clamp to >=1.
        """
        if isinstance(v, str):
            return v.strip()
        try:
            iv = int(v)
        except Exception:
            iv = 1
        return max(1, iv)

    @field_validator("unit_price")
    @classmethod
    def _unit_price_ok(cls, v):
        """
        - If it's a string (e.g., '1.234,56', '١٢٣٫٥٠'), keep as-is for ETL.
        - If it's numeric, clamp to >=0.
        """
        if isinstance(v, str):
            return v.strip()
        try:
            fv = float(v)
        except Exception:
            fv = 0.0
        return max(0.0, fv)

class InvoiceInput(BaseModel):
    vendor_name: str
    invoice_number: str
    date: str
    tax_id: str
    items: List[InvoiceItem]
    currency: str = "EUR"
    language: Optional[str] = None
    raw_text: Optional[str] = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("currency")
    @classmethod
    def _cur_upper(cls, v: str) -> str:
        return (v or "EUR").upper()

class Explanation(BaseModel):
    method: str
    details: Dict[str, Any]

class ExtractedFields(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    tax_id: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    line_count: Optional[int] = None

class InvoiceOutput(BaseModel):
    id: str
    extracted_fields: ExtractedFields
    language: str
    type_class: str
    type_confidence: float
    type_explanation: Explanation
    fraud_score: float = 0.0
    fraud_reasons: List[str] = Field(default_factory=list)
    tax_classification: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)
