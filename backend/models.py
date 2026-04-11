"""
Pydantic models — FacturAI Backend
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr


# ── Auth ──────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    plan: str


# ── Factura row ────────────────────────────────────────
class InvoiceRow(BaseModel):
    numero_factura: Optional[str]
    pagina: int
    fecha_literal: Optional[str]
    fecha_iso: Optional[str]
    total_eur: Optional[float]
    iva_pct: Optional[float] = 10
    base_eur: Optional[float]
    cuota_eur: Optional[float]
    estado: str
    observaciones: Optional[str]


# ── Conversión ─────────────────────────────────────────
class ConversionRecord(BaseModel):
    id: Optional[str]
    user_id: str
    filename: str
    pages: int
    completas: int
    verificar: int
    pendientes: int
    created_at: Optional[str]


# ── Planes ─────────────────────────────────────────────
PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    "free": {
        "label": "Free",
        "pdfs_per_month": 3,
        "max_pages": 10,
        "history_days": 7,
        "price_eur": 0,
        "stripe_price_id": None,
    },
    "basic": {
        "label": "Básico",
        "pdfs_per_month": 30,
        "max_pages": 50,
        "history_days": 30,
        "price_eur": 9,
        "stripe_price_id": "price_BASIC_PLACEHOLDER",
    },
    "pro": {
        "label": "Pro",
        "pdfs_per_month": 999_999,
        "max_pages": 200,
        "history_days": 365,
        "price_eur": 29,
        "stripe_price_id": "price_PRO_PLACEHOLDER",
    },
}


class PlanInfo(BaseModel):
    plan: str
    label: str
    pdfs_used: int
    pdfs_limit: int
    pages_limit: int
