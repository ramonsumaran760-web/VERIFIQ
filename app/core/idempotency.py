from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import IdempotencyKey


def get_cached_response(db: Session, *, client_id: str, endpoint: str, key: str) -> dict | None:
    row = (
        db.query(IdempotencyKey)
        .filter(
            IdempotencyKey.client_id == client_id,
            IdempotencyKey.endpoint == endpoint,
            IdempotencyKey.idempotency_key == key,
        )
        .first()
    )
    if not row:
        return None
    return {"status": row.response_status, "body": row.response_body}


def save_response(db: Session, *, client_id: str, endpoint: str, key: str, status: int, body: dict) -> None:
    entry = IdempotencyKey(
        client_id=client_id, endpoint=endpoint, idempotency_key=key,
        response_status=status, response_body=body,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        # Carrera: otra request con la misma key ya guardó primero. No pasa nada,
        # esa respuesta guardada es la que cuenta.
        db.rollback()
