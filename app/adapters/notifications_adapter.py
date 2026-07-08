"""
Antes, un KYC en manual_review o un AML flagged se quedaba silencioso hasta
que alguien lo consultara manualmente. Esto le avisa a tu equipo de compliance.

Real: POST a un webhook de Slack/Discord/email (configurable). Sin
NOTIFICATIONS_WEBHOOK_URL seteado, cae a modo mock y solo lo deja en logs +
en el audit_log (que ya de por sí queda registrado ahí).
"""
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger("verifiq.notifications")
settings = get_settings()


async def notify_ops(event_type: str, summary: str, details: dict) -> None:
    logger.warning("[NOTIFY][%s] %s | %s", event_type, summary, details)

    webhook_url = getattr(settings, "notifications_webhook_url", None)
    if not webhook_url:
        return  # modo mock: el log de arriba es la única notificación

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(webhook_url, json={"text": f"[{event_type}] {summary}", "details": details})
    except httpx.HTTPError as exc:
        # Una notificación fallida nunca debe tumbar el request principal
        # (el KYC/firma ya se guardó bien) — solo lo logueamos.
        logger.error("No se pudo enviar notificación a ops: %s", exc)
