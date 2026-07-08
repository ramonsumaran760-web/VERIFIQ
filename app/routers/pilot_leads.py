from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit import record_event
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.models import PilotLead
from app.schemas.schemas import PilotLeadCreate

router = APIRouter(prefix="/pilot-leads", tags=["pilot-leads"])


@router.post("", status_code=201)
@limiter.limit("5/minute")
def create_lead(request: Request, payload: PilotLeadCreate, db: Session = Depends(get_db)):
    if not payload.consent_privacidad:
        raise HTTPException(
            400,
            "Se requiere consentimiento explícito (Ley N.º 29733) para procesar estos datos.",
        )

    lead = PilotLead(
        empresa=payload.empresa,
        segmento=payload.segmento,
        email=payload.email,
        volumen_estimado=payload.volumen_estimado,
        consent_privacidad=payload.consent_privacidad,
        source_ip=request.client.host if request.client else None,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    record_event(
        db, actor="public_form", action="pilot_lead.create",
        resource_type="pilot_lead", resource_id=lead.id,
        ip_address=lead.source_ip,
    )
    return {"received": True, "id": lead.id}
