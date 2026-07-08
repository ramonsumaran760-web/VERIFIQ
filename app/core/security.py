"""
Seguridad de plataforma:

1. API keys de clientes: se generan, se muestran UNA sola vez al cliente, y solo
   se guarda su hash SHA-256 en la base de datos (nunca el valor en claro). Así,
   si la BD se filtra, las keys no quedan expuestas — igual que un password hash.

2. Cadena de hashes del audit log: cada evento de auditoría incluye el hash del
   evento anterior (blockchain-style, sin blockchain). Si alguien edita o borra
   una fila intermedia, la cadena deja de verificar y el manipuleo es detectable.
   Esto es lo que hace que el log sirva como evidencia legal, no solo un log.
"""
import hashlib
import hmac
import secrets


def generate_api_key(prefix: str = "vfq") -> str:
    """Genera una API key nueva en texto plano. Se muestra al cliente una sola vez."""
    token = secrets.token_urlsafe(32)
    return f"{prefix}_{token}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), stored_hash)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_audit_event_hash(prev_hash: str, event_payload: str) -> str:
    """
    Encadena el evento actual con el hash del anterior.
    prev_hash del primer evento de la tabla es "GENESIS".
    """
    combined = f"{prev_hash}|{event_payload}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()
