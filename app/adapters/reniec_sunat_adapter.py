from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.core.retry import with_provider_retry

settings = get_settings()


@with_provider_retry
async def _call_reniec(dni: str) -> httpx.Response:
    async with httpx.AsyncClient(base_url=settings.reniec_api_base_url, timeout=15) as client:
        resp = await client.get(
            f"/dni/{dni}",
            headers={"Authorization": f"Bearer {settings.reniec_api_token}"},
        )
        resp.raise_for_status()
        return resp


async def validate_dni(dni: str, full_name: str) -> dict:
    if not settings.reniec_api_base_url or not settings.reniec_api_token:
        return {
            "_mode": "mock",
            "valid": True,
            "full_name_match": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    resp = await _call_reniec(dni)
    data = resp.json()
    reniec_name = f"{data.get('nombres','')} {data.get('apellidoPaterno','')} {data.get('apellidoMaterno','')}".strip()
    return {
        "_mode": "real",
        "valid": True,
        "full_name_match": reniec_name.lower() == full_name.strip().lower(),
        "reniec_full_name": reniec_name,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@with_provider_retry
async def _call_sunat(ruc: str) -> httpx.Response:
    async with httpx.AsyncClient(base_url=settings.sunat_api_base_url, timeout=15) as client:
        resp = await client.get(
            f"/ruc/{ruc}",
            headers={"Authorization": f"Bearer {settings.sunat_api_token}"},
        )
        resp.raise_for_status()
        return resp


async def validate_ruc(ruc: str) -> dict:
    if not settings.sunat_api_base_url or not settings.sunat_api_token:
        return {"_mode": "mock", "valid": True, "estado": "ACTIVO", "condicion": "HABIDO"}

    resp = await _call_sunat(ruc)
    data = resp.json()
    data["_mode"] = "real"
    return data
