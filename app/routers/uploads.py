"""
Antes de esto, /signatures/sign y /kyc/verify asumían que ya tenías un
document_hash_sha256 o un storage_key — pero no había forma de generarlos.
Estos endpoints son ese eslabón faltante: reciben el archivo real, lo mandan
a storage_adapter (S3 SSE-KMS en real, disco local en dev), y devuelven la
referencia que los otros endpoints esperan.

Límite de tamaño: 15MB por archivo (selfies/DNIs no deberían pesar más que
eso; un PDF de contrato tampoco). Ajustable según tu caso de uso real.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.adapters import storage_adapter
from app.core.deps import get_current_client
from app.core.security import sha256_hex
from app.models.models import Client

router = APIRouter(prefix="/uploads", tags=["uploads"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_DOCUMENT_TYPES = {"application/pdf"}


async def _read_and_validate(file: UploadFile, allowed_types: set[str]) -> bytes:
    if file.content_type not in allowed_types:
        raise HTTPException(
            400, f"Tipo de archivo no permitido: {file.content_type}. Esperado: {allowed_types}"
        )
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Archivo excede el límite de {MAX_UPLOAD_BYTES // (1024*1024)}MB")
    if len(data) == 0:
        raise HTTPException(400, "Archivo vacío")
    return data


@router.post("/selfie")
async def upload_selfie(
    file: UploadFile,
    client: Client = Depends(get_current_client),
):
    data = await _read_and_validate(file, ALLOWED_IMAGE_TYPES)
    ext = file.content_type.split("/")[-1]
    storage_key = await storage_adapter.put_object(data, prefix=f"selfies/{client.id}", extension=ext)
    return {"storage_key": storage_key, "sha256": sha256_hex(data), "size_bytes": len(data)}


@router.post("/id-document")
async def upload_id_document(
    file: UploadFile,
    client: Client = Depends(get_current_client),
):
    data = await _read_and_validate(file, ALLOWED_IMAGE_TYPES)
    ext = file.content_type.split("/")[-1]
    storage_key = await storage_adapter.put_object(data, prefix=f"dnis/{client.id}", extension=ext)
    return {"storage_key": storage_key, "sha256": sha256_hex(data), "size_bytes": len(data)}


@router.post("/document")
async def upload_document(
    file: UploadFile,
    client: Client = Depends(get_current_client),
):
    """Para el PDF que se va a firmar. Devuelve el hash SHA-256 que luego se
    pasa a /signatures/sign — así el hash siempre corresponde al archivo real
    que quedó guardado, no a uno que el cliente pudo inventar en el JSON."""
    data = await _read_and_validate(file, ALLOWED_DOCUMENT_TYPES)
    storage_key = await storage_adapter.put_object(data, prefix=f"documents/{client.id}", extension="pdf")
    return {"storage_key": storage_key, "document_hash_sha256": sha256_hex(data), "size_bytes": len(data)}
