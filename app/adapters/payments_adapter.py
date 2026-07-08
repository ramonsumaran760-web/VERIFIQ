from datetime import datetime, timezone

import hashlib
import hmac

import httpx

from app.core.config import get_settings

settings = get_settings()


async def create_charge(*, amount_pen: float, client_email: str, token: str) -> dict:
    """
    A propósito, esta función NO tiene @with_provider_retry como los demás
    adapters. Reintentar un cobro que sí llegó a procesarse en el proveedor
    pero cuya respuesta se perdió por timeout duplicaría el cargo — eso es
    peor que fallar una vez y dejar que el idempotency_key de la capa de
    aplicación (ver /payments/charge) sea quien decida si reintentar.
    """
    if settings.payments_provider == "mock" or not settings.payments_secret_key:
        return {
            "_mode": "mock",
            "charge_id": f"mock_ch_{hashlib.sha256(client_email.encode()).hexdigest()[:12]}",
            "status": "paid",
            "amount_pen": amount_pen,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    if settings.payments_provider == "culqi":
        async with httpx.AsyncClient(base_url="https://api.culqi.com/v2", timeout=20) as client:
            resp = await client.post(
                "/charges",
                headers={"Authorization": f"Bearer {settings.payments_secret_key}"},
                json={
                    "amount": int(amount_pen * 100),  # Culqi usa céntimos
                    "currency_code": "PEN",
                    "email": client_email,
                    "source_id": token,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            data["_mode"] = "real"
            return data

    raise ValueError(f"payments_provider no soportado aún: {settings.payments_provider}")


def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    if not settings.payments_webhook_secret:
        return True  # modo mock: no hay secreto que verificar
    expected = hmac.new(
        settings.payments_webhook_secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
