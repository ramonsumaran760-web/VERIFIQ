from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.adapters import aml_adapter, kyc_adapter, notifications_adapter, reniec_sunat_adapter
from app.core.audit import record_event
from app.core.database import get_db
from app.core.deps import get_current_client
from app.core.idempotency import get_cached_response, save_response
from app.core.rate_limit import limiter
from app.models.models import Client, KycVerification, UsageEvent
from app.schemas.schemas import KycCreate, KycOut

router = APIRouter(prefix="/kyc", tags=["kyc"])

UNIT_COST_KYC_USD = 1.25
ENDPOINT_NAME = "kyc.verify"


def _decide_status(liveness_ok: bool, face_match: float, reniec_ok: bool, aml_status: str) -> str:
    if aml_status == "flagged":
        return "manual_review"
    if not liveness_ok or face_match < 0.85 or not reniec_ok:
        return "manual_review"
    return "approved"


@router.get("", response_model=list[KycOut])
def list_kyc(
    overall_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    query = db.query(KycVerification).filter(KycVerification.client_id == client.id)
    if overall_status:
        query = query.filter(KycVerification.overall_status == overall_status)
    return (
        query.order_by(KycVerification.created_at.desc())
        .offset(offset)
        .limit(min(limit, 200))
        .all()
    )


@router.post("/verify", response_model=KycOut, status_code=201)
@limiter.limit("20/minute")
async def verify(
    payload: KycCreate,
    request: Request,
    client: Client = Depends(get_current_client),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if idempotency_key:
        cached = get_cached_response(db, client_id=client.id, endpoint=ENDPOINT_NAME, key=idempotency_key)
        if cached:
            return cached["body"]

    face_result = await kyc_adapter.verify_liveness_and_match(
        payload.selfie_storage_key, payload.document_photo_storage_key
    )
    reniec_result = await reniec_sunat_adapter.validate_dni(
        payload.subject_document_number, payload.subject_full_name
    )
    aml_result = await aml_adapter.screen_person(
        payload.subject_full_name, payload.subject_document_number
    )

    overall = _decide_status(
        face_result["liveness_passed"],
        face_result["face_match_score"],
        reniec_result["valid"] and reniec_result["full_name_match"],
        aml_result["status"],
    )

    kyc = KycVerification(
        client_id=client.id,
        subject_document_number=payload.subject_document_number,
        subject_document_type=payload.subject_document_type,
        liveness_passed=face_result["liveness_passed"],
        face_match_score=face_result["face_match_score"],
        reniec_validated=reniec_result["valid"],
        reniec_full_name_match=reniec_result["full_name_match"],
        aml_status=aml_result["status"],
        aml_match_details=aml_result["matches"],
        selfie_storage_key=payload.selfie_storage_key,
        document_photo_storage_key=payload.document_photo_storage_key,
        overall_status=overall,
        decided_at=datetime.now(timezone.utc),
    )
    db.add(kyc)
    db.add(UsageEvent(client_id=client.id, event_type="kyc", unit_cost_usd=UNIT_COST_KYC_USD))
    db.commit()
    db.refresh(kyc)

    record_event(
        db, actor=str(request.state.api_key_id), action="kyc.verify",
        resource_type="kyc_verification", resource_id=kyc.id, client_id=client.id,
        metadata={
            "overall_status": overall,
            "aml_status": aml_result["status"],
            "modes": {
                "kyc": face_result.get("_mode"),
                "reniec": reniec_result.get("_mode"),
                "aml": aml_result.get("_mode"),
            },
        },
    )

    result = KycOut.model_validate(kyc).model_dump(mode="json")
    if idempotency_key:
        save_response(
            db, client_id=client.id, endpoint=ENDPOINT_NAME, key=idempotency_key,
            status=201, body=result,
        )

    if overall == "manual_review":
        await notifications_adapter.notify_ops(
            event_type="kyc.manual_review",
            summary=f"KYC de {payload.subject_full_name} requiere revisión manual",
            details={
                "kyc_id": kyc.id,
                "client_id": client.id,
                "aml_status": aml_result["status"],
                "face_match_score": face_result["face_match_score"],
                "reniec_ok": reniec_result["valid"] and reniec_result["full_name_match"],
            },
        )

    return kyc
