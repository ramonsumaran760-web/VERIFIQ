from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.adapters import psc_adapter
from app.core.audit import record_event
from app.core.database import get_db
from app.core.deps import get_current_client
from app.core.idempotency import get_cached_response, save_response
from app.core.rate_limit import limiter
from app.models.models import Client, SignatureRequest, UsageEvent
from app.schemas.schemas import ReSignCreate, SignatureCreate, SignatureOut, SignatureVerifyOut

router = APIRouter(prefix="/signatures", tags=["signatures"])

UNIT_COST_SIGN_USD = 0.55
ENDPOINT_NAME = "signatures.sign"


@router.post("/sign", response_model=SignatureOut, status_code=201)
@limiter.limit("60/minute")
async def sign(
    payload: SignatureCreate,
    request: Request,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if idempotency_key:
        cached = get_cached_response(db, client_id=client.id, endpoint=ENDPOINT_NAME, key=idempotency_key)
        if cached:
            return cached["body"]

    sig = SignatureRequest(
        client_id=client.id,
        signer_name=payload.signer_name,
        signer_email=payload.signer_email,
        signer_document_number=payload.signer_document_number,
        document_hash_sha256=payload.document_hash_sha256,
        signed_document_storage_key=payload.document_storage_key,
        signature_level=payload.signature_level,
        signer_ip=request.client.host if request.client else None,
        signer_user_agent=request.headers.get("user-agent"),
        status="pending",
    )

    if payload.signature_level == "digital_certificada":
        if not payload.signer_document_number:
            raise HTTPException(
                400, "signer_document_number es obligatorio para firma digital certificada"
            )
        cert = await psc_adapter.issue_ephemeral_certificate(
            payload.signer_name, payload.signer_document_number
        )
        sig.psc_provider = cert.get("provider", "mock")
        sig.psc_certificate_serial = cert["certificate_serial"]
        sig.padres_applied = cert.get("_mode") == "real"

    sig.status = "signed"
    sig.signed_at = datetime.now(timezone.utc)

    db.add(sig)
    db.add(UsageEvent(client_id=client.id, event_type="signature", unit_cost_usd=UNIT_COST_SIGN_USD))
    db.commit()
    db.refresh(sig)

    record_event(
        db, actor=str(request.state.api_key_id), action="signature.sign",
        resource_type="signature_request", resource_id=sig.id, client_id=client.id,
        ip_address=sig.signer_ip, user_agent=sig.signer_user_agent,
        metadata={"signature_level": sig.signature_level, "document_hash": sig.document_hash_sha256},
    )

    result = SignatureOut.model_validate(sig).model_dump(mode="json")
    if idempotency_key:
        save_response(
            db, client_id=client.id, endpoint=ENDPOINT_NAME, key=idempotency_key,
            status=201, body=result,
        )
    return sig


@router.get("", response_model=list[SignatureOut])
def list_signatures(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    query = db.query(SignatureRequest).filter(SignatureRequest.client_id == client.id)
    if status:
        query = query.filter(SignatureRequest.status == status)
    return (
        query.order_by(SignatureRequest.created_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )


@router.get("/verify/{signature_id}", response_model=SignatureVerifyOut)
def verify(
    signature_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    sig = (
        db.query(SignatureRequest)
        .filter(SignatureRequest.id == signature_id, SignatureRequest.client_id == client.id)
        .first()
    )
    if not sig:
        raise HTTPException(404, "Firma no encontrada")

    return SignatureVerifyOut(
        valid=sig.status in ("signed", "verified"),
        signature_level=sig.signature_level,
        signed_at=sig.signed_at,
        document_hash_sha256=sig.document_hash_sha256,
    )


@router.post("/{signature_id}/re-sign", response_model=SignatureOut, status_code=201)
@limiter.limit("30/minute")
async def re_sign(
    request: Request,
    signature_id: str,
    payload: ReSignCreate,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """
    Crea una NUEVA versión de una firma (ej: se corrigió una cláusula y hay
    que volver a firmar). La firma original NUNCA se edita ni se borra — sigue
    existiendo tal cual quedó, con su propio hash y su propia evidencia. Esto
    es clave si algún día hay que probar legalmente qué versión firmó quién.
    """
    parent = (
        db.query(SignatureRequest)
        .filter(SignatureRequest.id == signature_id, SignatureRequest.client_id == client.id)
        .first()
    )
    if not parent:
        raise HTTPException(404, "Firma original no encontrada")

    new_sig = SignatureRequest(
        client_id=client.id,
        signer_name=parent.signer_name,
        signer_email=parent.signer_email,
        signer_document_number=parent.signer_document_number,
        document_hash_sha256=payload.document_hash_sha256,
        signed_document_storage_key=payload.document_storage_key,
        signature_level=parent.signature_level,
        signer_ip=request.client.host if request.client else None,
        signer_user_agent=request.headers.get("user-agent"),
        version=parent.version + 1,
        parent_signature_id=parent.id,
        status="pending",
    )

    if parent.signature_level == "digital_certificada":
        cert = await psc_adapter.issue_ephemeral_certificate(
            parent.signer_name, parent.signer_document_number
        )
        new_sig.psc_provider = cert.get("provider", "mock")
        new_sig.psc_certificate_serial = cert["certificate_serial"]
        new_sig.padres_applied = cert.get("_mode") == "real"

    new_sig.status = "signed"
    new_sig.signed_at = datetime.now(timezone.utc)

    db.add(new_sig)
    db.add(UsageEvent(client_id=client.id, event_type="signature", unit_cost_usd=UNIT_COST_SIGN_USD))
    db.commit()
    db.refresh(new_sig)

    record_event(
        db, actor=str(request.state.api_key_id), action="signature.re_sign",
        resource_type="signature_request", resource_id=new_sig.id, client_id=client.id,
        metadata={"parent_signature_id": parent.id, "version": new_sig.version},
    )
    return new_sig


@router.get("/{signature_id}/versions", response_model=list[SignatureOut])
def version_history(
    signature_id: str,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    """Devuelve toda la cadena de versiones (original + re-firmas), en orden."""
    sig = (
        db.query(SignatureRequest)
        .filter(SignatureRequest.id == signature_id, SignatureRequest.client_id == client.id)
        .first()
    )
    if not sig:
        raise HTTPException(404, "Firma no encontrada")

    root_id = sig.parent_signature_id or sig.id
    chain = (
        db.query(SignatureRequest)
        .filter(
            SignatureRequest.client_id == client.id,
            (SignatureRequest.id == root_id) | (SignatureRequest.parent_signature_id == root_id),
        )
        .order_by(SignatureRequest.version.asc())
        .all()
    )
    return chain
