"""
Autenticación JWT via Supabase — FacturAI Backend
Verifica tokens preguntando directamente a Supabase (más fiable que verificar localmente).
"""
import os
import logging
from typing import Dict, Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import get_supabase

logger = logging.getLogger(__name__)
bearer = HTTPBearer()


async def verify_token_with_supabase(token: str) -> Dict[str, Any]:
    """
    Verifica el token preguntando a la API de Supabase /auth/v1/user.
    Es el método más fiable — Supabase valida su propio token.
    """
    supabase_url     = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{supabase_url}/auth/v1/user",
            headers={
                "apikey":        service_role_key,
                "Authorization": f"Bearer {token}",
            },
            timeout=10,
        )

    if resp.status_code != 200:
        logger.warning(f"Token rechazado por Supabase: {resp.status_code} {resp.text[:100]}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return resp.json()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> Dict[str, Any]:
    """
    Dependencia FastAPI: verifica el token con Supabase y devuelve el usuario.
    """
    user_data = await verify_token_with_supabase(credentials.credentials)
    user_id   = user_data.get("id")

    if not user_id:
        raise HTTPException(status_code=401, detail="Token sin user_id.")

    # Obtener perfil (plan, cuota)
    try:
        sb      = get_supabase()
        resp    = sb.table("profiles").select("*").eq("id", user_id).single().execute()
        profile = resp.data or {}
    except Exception as e:
        logger.error(f"Error obteniendo perfil {user_id}: {e}")
        profile = {}

    return {
        "user_id":         user_id,
        "email":           user_data.get("email", ""),
        "plan":            profile.get("plan", "free"),
        "pdfs_used_month": profile.get("pdfs_used_month", 0),
        "profile":         profile,
    }


async def require_active_subscription(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Verifica que el usuario tenga cuota disponible según su plan.
    """
    from models import PLAN_LIMITS
    plan   = user["plan"]
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    used   = user.get("pdfs_used_month", 0)

    if used >= limits["pdfs_per_month"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Has alcanzado el límite de {limits['pdfs_per_month']} PDFs/mes "
                   f"del plan {limits['label']}. Actualiza tu plan para continuar.",
        )
    return user
