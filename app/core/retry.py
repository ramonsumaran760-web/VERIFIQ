"""
Retry con backoff exponencial para llamadas a proveedores externos (PSC, KYC,
RENIEC/SUNAT, AML, pagos). Sin esto, si un proveedor tiene un timeout aislado
o un 502 pasajero, el request completo del cliente fallaba en seco.

Reintenta solo errores transitorios (timeout, error de conexión, 5xx) — NUNCA
reintenta un 4xx, porque eso es un error del propio request (no tiene sentido
repetir algo que el proveedor ya rechazó por datos inválidos).
"""
import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def with_provider_retry(func):
    """Decorator listo para usar en funciones async que llaman a un proveedor externo."""
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=retry_if_exception(_is_transient_error),
    )(func)
