import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import compute_audit_event_hash
from app.models.models import AuditLog

GENESIS = "GENESIS"


def _get_last_hash(db: Session) -> str:
    last = db.execute(
        select(AuditLog.event_hash).order_by(AuditLog.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    return last or GENESIS


def record_event(
    db: Session,
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    client_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    prev_hash = _get_last_hash(db)
    created_at = datetime.utcnow()
    payload = json.dumps(
        {
            "actor": actor,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "metadata": metadata or {},
            "ts": created_at.isoformat(),
        },
        sort_keys=True,
        default=str,
    )
    event_hash = compute_audit_event_hash(prev_hash, payload)

    entry = AuditLog(
        client_id=client_id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_json=metadata or {},
        prev_hash=prev_hash,
        event_hash=event_hash,
        created_at=created_at,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify_chain(db: Session) -> tuple[bool, str | None]:
    """Recorre toda la tabla y re-calcula los hashes. Si algo fue alterado,
    la cadena rompe en el primer evento inconsistente."""
    rows = db.execute(select(AuditLog).order_by(AuditLog.created_at.asc())).scalars().all()
    prev = GENESIS
    for row in rows:
        payload = json.dumps(
            {
                "actor": row.actor,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "metadata": row.metadata_json or {},
                "ts": row.created_at.isoformat(),
            },
            sort_keys=True,
            default=str,
        )
        expected = compute_audit_event_hash(prev, payload)
        if row.prev_hash != prev or row.event_hash != expected:
            return False, row.id
        prev = row.event_hash
    return True, None
