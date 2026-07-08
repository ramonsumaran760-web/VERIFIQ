"""
Storage cifrado para PDFs firmados y fotos de DNI/selfies.

Real: S3 con SSE-KMS (server-side encryption) + URLs firmadas temporales
(nunca URLs públicas permanentes). Dev: disco local en /tmp, solo para pruebas.
"""
import os
import uuid

from app.core.config import get_settings

settings = get_settings()
LOCAL_STORAGE_DIR = "/tmp/verifiq_storage"


def _local_put(key: str, data: bytes) -> str:
    os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)
    path = os.path.join(LOCAL_STORAGE_DIR, key.replace("/", "_"))
    with open(path, "wb") as f:
        f.write(data)
    return key


async def put_object(data: bytes, *, prefix: str, extension: str) -> str:
    key = f"{prefix}/{uuid.uuid4()}.{extension}"

    if settings.storage_backend == "local" or not settings.s3_bucket:
        return _local_put(key, data)

    # --- Real: boto3 con SSE-KMS ---
    # import boto3
    # s3 = boto3.client(
    #     "s3",
    #     aws_access_key_id=settings.aws_access_key_id,
    #     aws_secret_access_key=settings.aws_secret_access_key,
    #     region_name=settings.aws_region,
    # )
    # s3.put_object(
    #     Bucket=settings.s3_bucket,
    #     Key=key,
    #     Body=data,
    #     ServerSideEncryption="aws:kms",
    #     SSEKMSKeyId=settings.s3_kms_key_id,
    # )
    raise NotImplementedError(
        "Storage S3 real pendiente de credenciales AWS. Ver comentario en put_object()."
    )


async def get_presigned_url(key: str, expires_seconds: int = 300) -> str:
    if settings.storage_backend == "local" or not settings.s3_bucket:
        return f"local://{LOCAL_STORAGE_DIR}/{key.replace('/', '_')}"

    # import boto3
    # s3 = boto3.client("s3", region_name=settings.aws_region)
    # return s3.generate_presigned_url(
    #     "get_object", Params={"Bucket": settings.s3_bucket, "Key": key},
    #     ExpiresIn=expires_seconds,
    # )
    raise NotImplementedError("Presigned URL real pendiente de credenciales AWS.")
