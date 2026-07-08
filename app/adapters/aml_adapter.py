from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.core.retry import with_provider_retry

settings = get_settings()

# Nombres usados solo para la demo del modo mock — nunca se usan en modo real.
_MOCK_WATCHLIST_HINTS = {"sancionado", "test-flagged"}


@with_provider_retry
async def _call_complyadvantage(full_name: str) -> httpx.Response:
    async with httpx.AsyncClient(base_url=settings.aml_api_base_url, timeout=20) as client:
        resp = await client.post(
            "/searches",
            headers={"Authorization": f"Token {settings.aml_api_key}"},
            json={"search_term": full_name, "filters": {"types": ["sanction", "pep", "warning"]}},
        )
        resp.raise_for_status()
        return resp


async def screen_person(full_name: str, dni: str | None = None) -> dict:
    if settings.aml_provider == "mock" or not settings.aml_api_key:
        flagged = full_name.strip().lower() in _MOCK_WATCHLIST_HINTS
        return {
            "_mode": "mock",
            "status": "flagged" if flagged else "clear",
            "matches": [],
            "screened_at": datetime.now(timezone.utc).isoformat(),
        }

    resp = await _call_complyadvantage(full_name)
    data = resp.json()
    hits = data.get("content", {}).get("data", {}).get("hits", [])
    return {
        "_mode": "real",
        "status": "flagged" if hits else "clear",
        "matches": hits,
        "screened_at": datetime.now(timezone.utc).isoformat(),
    }
