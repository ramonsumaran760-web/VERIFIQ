"""
Antes, el tipo de cambio USD->PEN estaba hardcodeado en 3.75 en todo el código.
Esto lo reemplaza por una consulta a una API pública de cambio, con:
  - Cache en memoria de 1 hora (no tiene sentido pegarle a la API en cada
    request de /usage/summary).
  - Fallback al valor hardcodeado si la API externa falla — un tipo de cambio
    "casi correcto" es mejor que un 500 en el endpoint de facturación.
"""
import logging
import time

import httpx

logger = logging.getLogger("verifiq.exchange_rate")

FALLBACK_RATE_PEN = 3.75
CACHE_TTL_SECONDS = 3600
_cache: dict = {"rate": None, "fetched_at": 0.0}


async def get_usd_to_pen_rate() -> float:
    now = time.monotonic()
    if _cache["rate"] is not None and (now - _cache["fetched_at"]) < CACHE_TTL_SECONDS:
        return _cache["rate"]

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("https://api.exchangerate-api.com/v4/latest/USD")
            resp.raise_for_status()
            rate = resp.json()["rates"]["PEN"]
            _cache["rate"] = rate
            _cache["fetched_at"] = now
            return rate
    except (httpx.HTTPError, KeyError) as exc:
        logger.warning("No se pudo obtener tipo de cambio en vivo, usando fallback: %s", exc)
        return FALLBACK_RATE_PEN
