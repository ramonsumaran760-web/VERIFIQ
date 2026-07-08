"""
Adapter de firma digital certificada.

Modo real (psc_provider != "mock"):
  1. Pide al PSC (Camerfirma, IO Digital, etc.) un certificado efímero para el
     firmante, tras validar su identidad (ver kyc_adapter).
  2. Usa pyhanko para incrustar la firma en el PDF como PAdES-BES/LTV, incluyendo
     sello de tiempo RFC 3161 (TSA) y referencia a CRL/OCSP para validación
     a largo plazo.

Modo mock (default, sin credenciales configuradas):
  Genera un hash + "sello" simulado, y lo marca explícitamente con
  `_mode: "mock"` para que nunca se confunda con una firma certificada real.
  Esto es lo que hoy el landing llama "firma electrónica simple con evidencia
  técnica" — sigue siendo válido para ese nivel, solo no es PAdES certificado.
"""
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.core.retry import with_provider_retry
from app.core.security import sha256_hex

settings = get_settings()


class PscAdapterError(Exception):
    pass


@with_provider_retry
async def _call_psc_issue_certificate(signer_name: str, signer_document_number: str) -> httpx.Response:
    async with httpx.AsyncClient(base_url=settings.psc_api_base_url, timeout=20) as client:
        resp = await client.post(
            "/certificates/ephemeral",
            headers={"Authorization": f"Bearer {settings.psc_api_key}"},
            json={"subject_name": signer_name, "subject_document": signer_document_number},
        )
        resp.raise_for_status()
        return resp


async def issue_ephemeral_certificate(signer_name: str, signer_document_number: str) -> dict:
    """Solicita al PSC un certificado efímero para este firmante y transacción."""
    if settings.psc_provider == "mock" or not settings.psc_api_key:
        return {
            "_mode": "mock",
            "certificate_serial": f"MOCK-{sha256_hex(signer_document_number.encode())[:16]}",
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "provider": "mock",
        }

    try:
        resp = await _call_psc_issue_certificate(signer_name, signer_document_number)
    except httpx.HTTPStatusError as exc:
        raise PscAdapterError(f"PSC error {exc.response.status_code}: {exc.response.text}") from exc
    data = resp.json()
    data["_mode"] = "real"
    return data


def embed_pades_signature(pdf_bytes: bytes, certificate_info: dict) -> bytes:
    """
    Incrusta la firma PAdES en el PDF usando pyhanko.

    NOTA DE IMPLEMENTACIÓN: en modo real esto requiere el certificado y llave
    privada del PSC cargados vía pyhanko.sign.signers.SimpleSigner, más el
    cliente de sello de tiempo (pyhanko.sign.timestamps.HTTPTimeStamper contra
    `settings.psc_tsa_url`). Se deja como función separada y pura (bytes -> bytes)
    para que sea testeable sin red, y para que el modo mock devuelva el mismo
    tipo de dato que el modo real.
    """
    if certificate_info.get("_mode") == "mock":
        # No se firma de verdad el PDF; se devuelve tal cual + se registra
        # el hash en signature_requests.document_hash_sha256 como evidencia.
        return pdf_bytes

    # --- Integración real (requiere pyhanko + credenciales del PSC) ---
    # from pyhanko.sign import signers, timestamps
    # from pyhanko.sign.fields import SigFieldSpec, append_signature_field
    # signer = signers.SimpleSigner.load(
    #     key_file=..., cert_file=..., ca_chain_files=[...]
    # )
    # timestamper = timestamps.HTTPTimeStamper(settings.psc_tsa_url)
    # ... pdf_signer.sign_pdf(...) con LTVEnabled=True
    raise NotImplementedError(
        "Firma PAdES real pendiente de credenciales del PSC contratado. "
        "Ver comentario en embed_pades_signature() para el flujo con pyhanko."
    )
