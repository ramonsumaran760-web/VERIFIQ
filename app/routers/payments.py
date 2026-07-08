from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.adapters import payments_adapter
from app.core.audit import record_event
from app.core.database import get_db
from app.core.deps import get_current_client
from app.core.idempotency import get_cached_response, save_response
from app.core.rate_limit import limiter
from app.models.models import Client, Payment

router = APIRouter(prefix="/payments", tags=["payments"])

PLAN_PRICES_PEN = {"starter": 0, "growth": 399, "enterprise": None}
ENDPOINT_NAME = "payments.charge"


@router.post("/charge", status_code=201)
@limiter.limit("10/minute")
async def create_charge(
    request: Request,
    plan: str,
    token: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    # Para cobros, el idempotency_key es OBLIGATORIO en la práctica (no solo
    # opcional como en firmas/KYC) — un cobro duplicado es dinero real perdido.
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key es obligatorio para /payments/charge")

    cached = get_cached_response(db, client_id=client.id, endpoint=ENDPOINT_NAME, key=idempotency_key)
    if cached:
        return cached["body"]

    amount = PLAN_PRICES_PEN.get(plan)
    if amount is None:
        raise HTTPException(400, "Plan inválido o requiere cotización manual (enterprise)")

    result = await payments_adapter.create_charge(
        amount_pen=amount, client_email=client.contact_email, token=token
    )

    payment = Payment(
        client_id=client.id,
        provider=result.get("provider", "mock"),
        provider_charge_id=result["charge_id"],
        amount_pen=amount,
        status=result["status"],
        plan=plan,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    record_event(
        db, actor="system", action="payment.charge", resource_type="payment",
        resource_id=payment.id, client_id=client.id, metadata={"plan": plan, "status": payment.status},
    )

    response = {"payment_id": payment.id, "status": payment.status}
    save_response(
        db, client_id=client.id, endpoint=ENDPOINT_NAME, key=idempotency_key,
        status=201, body=response,
    )
    return response


@router.post("/webhook")
async def payment_webhook(request: Request, x_signature: str = Header(default=""), db: Session = Depends(get_db)):
    body = await request.body()
    if not payments_adapter.verify_webhook_signature(body, x_signature):
        raise HTTPException(401, "Firma de webhook inválida")

    payload = await request.json()
    charge_id = payload.get("charge_id")
    new_status = payload.get("status")

    payment = db.query(Payment).filter(Payment.provider_charge_id == charge_id).first()
    if payment:
        payment.status = new_status
        db.commit()
        record_event(
            db, actor="payments_webhook", action="payment.webhook",
            resource_type="payment", resource_id=payment.id, client_id=payment.client_id,
            metadata={"new_status": new_status},
        )
    return {"received": True}
