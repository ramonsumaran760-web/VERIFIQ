from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.audit import record_event
from app.core.database import get_db
from app.core.deps import require_admin
from app.core.security import generate_api_key, hash_api_key
from app.models.models import ApiKey, Client
from app.schemas.schemas import ApiKeyCreated, ClientCreate, ClientOut

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=list[ClientOut], dependencies=[Depends(require_admin)])
def list_clients(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return (
        db.query(Client).order_by(Client.created_at.desc()).offset(offset).limit(min(limit, 200)).all()
    )


@router.get("/{client_id}", response_model=ClientOut, dependencies=[Depends(require_admin)])
def get_client(client_id: str, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Cliente no encontrado")
    return client


@router.post("", response_model=ClientOut, status_code=201, dependencies=[Depends(require_admin)])
def create_client(payload: ClientCreate, db: Session = Depends(get_db)):
    client = Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)

    record_event(
        db, actor="admin", action="client.create",
        resource_type="client", resource_id=client.id,
    )
    return client


@router.post(
    "/{client_id}/api-keys",
    response_model=ApiKeyCreated,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def create_api_key(client_id: str, sandbox: bool = True, db: Session = Depends(get_db)):
    raw_key = generate_api_key(prefix="vfq_sb" if sandbox else "vfq")
    key = ApiKey(
        client_id=client_id,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[:14],
        is_sandbox=sandbox,
    )
    db.add(key)
    db.commit()
    db.refresh(key)

    record_event(
        db, actor="admin", action="apikey.create",
        resource_type="api_key", resource_id=key.id, client_id=client_id,
    )
    return ApiKeyCreated(
        id=key.id, raw_key=raw_key, key_prefix=key.key_prefix, is_sandbox=key.is_sandbox
    )
