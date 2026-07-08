"""
Rate limiting real con slowapi (wrapper de limits sobre in-memory storage por
defecto). Para producción con más de una instancia del API corriendo,
cambiar el storage a Redis (ver comentario en get_limiter) — con memoria local
cada instancia lleva su propio contador, lo cual permite un poco más de tráfico
del límite nominal si hay varias réplicas, pero sigue protegiendo contra abuso.

La key del límite es la API key del cliente cuando existe (así un cliente no
puede afectar a otro), y cae a IP para endpoints públicos como /pilot-leads.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_key(request) -> str:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"apikey:{api_key[:20]}"
    return f"ip:{get_remote_address(request)}"


# Real: Limiter(key_func=_rate_limit_key, storage_uri="redis://localhost:6379")
limiter = Limiter(key_func=_rate_limit_key, storage_uri="memory://")
