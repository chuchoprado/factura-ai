"""
FacturAI — Backend principal (FastAPI)
Convierte PDFs de facturas a Excel con Claude Vision.
"""
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List

import anthropic
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, Form, HTTPException,
    Request, UploadFile, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from auth         import get_current_user, require_active_subscription
from billing      import create_checkout_session, create_portal_session, handle_stripe_webhook
from database     import get_supabase, get_supabase_anon
from extract      import create_invoice_excel, extract_invoice_from_page, pdf_to_page_images, sort_and_renumber_rows
from models       import PLAN_LIMITS, PlanInfo
from telegram_bot import process_update

load_dotenv(override=True)

logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")
FRONTEND_URL    = os.getenv("FRONTEND_URL", "http://localhost:3000")


# ─────────────────────────────────────────────
# CICLO DE VIDA
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FacturAI backend iniciado ✅")
    yield
    logger.info("FacturAI backend detenido")


app = FastAPI(
    title="FacturAI API",
    version="1.0.0",
    description="Convierte PDFs de facturas a Excel con IA",
    lifespan=lifespan,
)

# CORS — permite localhost en dev y el dominio de producción en Vercel
_allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    FRONTEND_URL,
]
# Añadir subdominios de Vercel automáticamente
VERCEL_URL = os.getenv("VERCEL_URL", "")
if VERCEL_URL:
    _allowed_origins.append(f"https://{VERCEL_URL}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────

@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "service": "FacturAI API", "version": "1.0.0"}


@app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


# ─────────────────────────────────────────────
# AUTH — Registro / Login via Supabase
# ─────────────────────────────────────────────

@app.post("/auth/register", tags=["auth"])
async def register(email: str = Form(...), password: str = Form(...), full_name: str = Form("")):
    """Registro — crea usuario confirmado via Admin REST API de Supabase."""
    import httpx
    supabase_url     = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{supabase_url}/auth/v1/admin/users",
                headers={
                    "apikey":        service_role_key,
                    "Authorization": f"Bearer {service_role_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "email":          email,
                    "password":       password,
                    "email_confirm":  True,
                    "user_metadata":  {"full_name": full_name},
                },
                timeout=15,
            )

        if resp.status_code not in (200, 201):
            body = resp.json()
            msg  = body.get("msg") or body.get("message") or "Error al crear la cuenta."
            raise HTTPException(status_code=400, detail=msg)

        user_id = resp.json().get("id")
        return {"message": "Cuenta creada. Ya puedes iniciar sesión.", "user_id": user_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registro: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@app.post("/auth/login", tags=["auth"])
async def login(email: str = Form(...), password: str = Form(...)):
    """Login — llama directamente a la API REST de Supabase Auth."""
    import httpx
    supabase_url     = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{supabase_url}/auth/v1/token?grant_type=password",
                headers={
                    "apikey":       service_role_key,
                    "Content-Type": "application/json",
                },
                json={"email": email, "password": password},
                timeout=15,
            )

        if resp.status_code != 200:
            body = resp.json()
            msg  = body.get("error_description") or body.get("msg") or "Credenciales incorrectas."
            logger.warning(f"Login fallido para {email}: {msg}")
            raise HTTPException(status_code=401, detail=msg)

        data         = resp.json()
        access_token = data["access_token"]
        user_info    = data.get("user", {})
        user_id      = user_info.get("id")
        user_email   = user_info.get("email")

        # Obtener plan del perfil
        sb = get_supabase()
        try:
            profile = sb.table("profiles").select("plan").eq("id", user_id).single().execute()
            plan    = profile.data.get("plan", "free") if profile.data else "free"
        except Exception:
            plan = "free"

        return {
            "access_token": access_token,
            "token_type":   "bearer",
            "user_id":      user_id,
            "email":        user_email,
            "plan":         plan,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inesperado en login: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


# ─────────────────────────────────────────────
# USUARIO — Perfil y plan
# ─────────────────────────────────────────────

@app.get("/user/me", tags=["user"])
async def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    """Devuelve el perfil y estado del plan del usuario autenticado."""
    plan   = user["plan"]
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    return {
        "user_id":   user["user_id"],
        "email":     user["email"],
        "plan":      plan,
        "plan_label": limits["label"],
        "pdfs_used":  user.get("pdfs_used_month", 0),
        "pdfs_limit": limits["pdfs_per_month"],
        "pages_limit": limits["max_pages"],
        "profile":   user.get("profile", {}),
    }


# ─────────────────────────────────────────────
# EXTRACCIÓN — PDF → Excel
# ─────────────────────────────────────────────

@app.post("/extract", tags=["extract"])
async def extract_pdf(
    file: UploadFile = File(...),
    tipo: str        = Form("autonomo"),   # "autonomo" o "gastos_pf"
    user: Dict[str, Any] = Depends(require_active_subscription),
):
    """
    Recibe un PDF, extrae las facturas con Claude Vision y devuelve un Excel.
    - tipo: 'autonomo' | 'gastos_pf'
    - Requiere token JWT válido y cuota disponible.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF.")

    plan   = user["plan"]
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    pdf_bytes = await file.read()

    # ── Convertir páginas ──
    try:
        page_images = await asyncio.to_thread(pdf_to_page_images, pdf_bytes)
    except Exception as e:
        logger.error(f"Error renderizando PDF: {e}")
        raise HTTPException(status_code=422, detail="No se pudo procesar el PDF.")

    if not page_images:
        raise HTTPException(status_code=422, detail="El PDF no tiene páginas legibles.")

    max_pages = limits["max_pages"]
    if len(page_images) > max_pages:
        raise HTTPException(
            status_code=400,
            detail=f"El PDF tiene {len(page_images)} páginas. Tu plan '{limits['label']}' permite máx. {max_pages} páginas.",
        )

    # ── Extracción con Claude ──
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    rows: List[Dict[str, Any]] = []
    for idx, page_b64 in enumerate(page_images, start=1):
        row = await extract_invoice_from_page(client, page_b64, idx, ANTHROPIC_MODEL)
        rows.append(row)

    rows = sort_and_renumber_rows(rows)

    # ── Generar Excel en memoria ──
    excel_bytes = create_invoice_excel(rows)

    # ── Guardar historial en Supabase ──
    completas  = sum(1 for r in rows if r["estado"] == "COMPLETA")
    verificar  = sum(1 for r in rows if r["estado"] == "VERIFICAR_DATOS")
    pendientes = sum(1 for r in rows if r["estado"] == "PENDIENTE_REVISION")

    try:
        sb = get_supabase()
        sb.table("conversions").insert({
            "user_id":   user["user_id"],
            "filename":  file.filename or "sin_nombre.pdf",
            "pages":     len(rows),
            "completas": completas,
            "verificar": verificar,
            "pendientes": pendientes,
            "tipo":      tipo,
        }).execute()

        # Incrementar contador mensual
        sb.rpc("increment_pdfs_used", {"uid": user["user_id"]}).execute()
    except Exception as e:
        logger.warning(f"Error guardando historial: {e}")

    # ── Nombre del archivo de salida ──
    month_year  = datetime.now().strftime("%m%Y")
    output_name = f"Facturas_{tipo}_{month_year}.xlsx"

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
    )


# ─────────────────────────────────────────────
# HISTORIAL
# ─────────────────────────────────────────────

@app.get("/history", tags=["history"])
async def get_history(user: Dict[str, Any] = Depends(get_current_user)):
    """Devuelve el historial de conversiones del usuario."""
    plan   = user["plan"]
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    days   = limits["history_days"]

    sb = get_supabase()
    try:
        res = (
            sb.table("conversions")
            .select("*")
            .eq("user_id", user["user_id"])
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        return {"conversions": res.data or [], "history_days": days}
    except Exception as e:
        logger.error(f"Error obteniendo historial: {e}")
        return {"conversions": [], "history_days": days}


# ─────────────────────────────────────────────
# BILLING — Stripe
# ─────────────────────────────────────────────

@app.post("/billing/checkout", tags=["billing"])
async def checkout(
    plan: str = Form(...),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Crea sesión de checkout Stripe para subir de plan."""
    url = await create_checkout_session(
        user_id      = user["user_id"],
        user_email   = user["email"],
        plan         = plan,
        success_url  = f"{FRONTEND_URL}/dashboard?upgrade=success",
        cancel_url   = f"{FRONTEND_URL}/pricing",
    )
    return {"checkout_url": url}


@app.post("/billing/portal", tags=["billing"])
async def billing_portal(user: Dict[str, Any] = Depends(get_current_user)):
    """Abre el portal Stripe del cliente para gestionar su suscripción."""
    profile     = user.get("profile", {})
    customer_id = profile.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No tienes una suscripción activa.")
    url = await create_portal_session(
        stripe_customer_id=customer_id,
        return_url=f"{FRONTEND_URL}/dashboard",
    )
    return {"portal_url": url}


@app.post("/billing/webhook", tags=["billing"], include_in_schema=False)
async def stripe_webhook(request: Request):
    """Endpoint para webhooks de Stripe (sin autenticación JWT)."""
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    sb         = get_supabase()
    result     = await handle_stripe_webhook(payload, sig_header, sb)
    return result


# ─────────────────────────────────────────────
# TELEGRAM BOT — Webhook
# ─────────────────────────────────────────────

@app.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Recibe updates de Telegram — responde 200 inmediato y procesa en background."""
    try:
        update = await request.json()
        background_tasks.add_task(process_update, update)
    except Exception as e:
        logger.error(f"Error en telegram webhook: {e}")
    return {"ok": True}
