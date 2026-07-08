from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_api_key
from app.models.models import ApiKey, Client

settings = get_settings()


def require_admin(x_admin_token: str = Header(..., alias="X-Admin-Token")) -> None:
    """
    Protege endpoints internos (crear clientes, emitir API keys). Este token es
    tuyo/de tu equipo — nunca del cliente final. En producción, además de esto,
    lo ideal es que estos endpoints ni siquiera estén expuestos públicamente
    (solo accesibles desde tu VPN/red interna o un panel admin autenticado).
    """
    import hmac

    if not hmac.compare_digest(x_admin_token, settings.admin_api_token):
        raise HTTPException(status_code=401, detail="Token de administrador inválido")


def get_current_client(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Client:
    key_hash = hash_api_key(x_api_key)
    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
        .first()
    )
    if not api_key:
        raise HTTPException(status_code=401, detail="API key inválida o revocada")

    client = db.query(Client).filter(Client.id == api_key.client_id, Client.is_active.is_(True)).first()
    if not client:
        raise HTTPException(status_code=401, detail="Cliente inactivo")

    request.state.api_key_id = api_key.id
    request.state.client_id = client.id
    return client
