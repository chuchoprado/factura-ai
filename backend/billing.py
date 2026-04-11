"""
Stripe — Suscripciones y pagos — FacturAI Backend
"""
import os
import logging
from typing import Dict, Any, Optional

import stripe
from fastapi import HTTPException

from models import PLAN_LIMITS

logger = logging.getLogger(__name__)


def get_stripe():
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return stripe


# ─────────────────────────────────────────────
# CREAR SESIÓN DE CHECKOUT
# ─────────────────────────────────────────────

async def create_checkout_session(
    user_id: str,
    user_email: str,
    plan: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Crea una sesión de pago Stripe y devuelve la URL de checkout."""
    st = get_stripe()
    limits = PLAN_LIMITS.get(plan)
    if not limits or not limits.get("stripe_price_id"):
        raise HTTPException(status_code=400, detail=f"Plan '{plan}' no válido o sin precio Stripe.")

    try:
        session = st.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            customer_email=user_email,
            line_items=[{"price": limits["stripe_price_id"], "quantity": 1}],
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            metadata={"user_id": user_id, "plan": plan},
            subscription_data={"metadata": {"user_id": user_id, "plan": plan}},
        )
        return session.url
    except stripe.error.StripeError as e:
        logger.error(f"Error Stripe checkout: {e}")
        raise HTTPException(status_code=500, detail="Error al crear sesión de pago.")


# ─────────────────────────────────────────────
# PORTAL DE CLIENTE (gestionar suscripción)
# ─────────────────────────────────────────────

async def create_portal_session(stripe_customer_id: str, return_url: str) -> str:
    """Devuelve URL del portal de Stripe para gestionar/cancelar suscripción."""
    st = get_stripe()
    try:
        session = st.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return session.url
    except stripe.error.StripeError as e:
        logger.error(f"Error Stripe portal: {e}")
        raise HTTPException(status_code=500, detail="Error al abrir portal de facturación.")


# ─────────────────────────────────────────────
# WEBHOOK — Actualizar plan en Supabase
# ─────────────────────────────────────────────

async def handle_stripe_webhook(payload: bytes, sig_header: str, supabase_client) -> Dict[str, Any]:
    """
    Procesa eventos Stripe y actualiza el plan del usuario en Supabase.
    Eventos manejados:
      - checkout.session.completed  → activa plan
      - customer.subscription.deleted → vuelve a free
      - invoice.payment_failed       → notifica
    """
    st     = get_stripe()
    secret = os.environ["STRIPE_WEBHOOK_SECRET"]

    try:
        event = st.Webhook.construct_event(payload, sig_header, secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Firma Stripe inválida.")

    event_type = event["type"]
    data       = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("metadata", {}).get("user_id")
        plan    = data.get("metadata", {}).get("plan", "free")
        customer_id = data.get("customer")
        if user_id:
            supabase_client.table("profiles").update({
                "plan": plan,
                "stripe_customer_id": customer_id,
                "subscription_status": "active",
            }).eq("id", user_id).execute()
            logger.info(f"Plan activado: user={user_id} plan={plan}")

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id:
            supabase_client.table("profiles").update({
                "plan": "free",
                "subscription_status": "cancelled",
            }).eq("stripe_customer_id", customer_id).execute()
            logger.info(f"Suscripción cancelada: customer={customer_id}")

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        logger.warning(f"Pago fallido para customer={customer_id}")

    return {"received": True, "type": event_type}
