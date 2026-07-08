"""
KYC biométrico: liveness detection + face match contra la foto del DNI.

En producción el selfie NUNCA debería llegar en base64 dentro del JSON del
endpoint público sin pasar antes por este adapter — se sube directo al
proveedor (Incode/AWS Rekognition) o a storage cifrado, y aquí solo se maneja
la referencia (storage_key) + el resultado del scoring.
"""
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.core.retry import with_provider_retry

settings = get_settings()


@with_provider_retry
async def _call_incode_liveness(selfie_storage_key: str, id_photo_storage_key: str) -> httpx.Response:
    async with httpx.AsyncClient(base_url=settings.kyc_api_base_url, timeout=30) as client:
        resp = await client.post(
            "/omni/liveness",
            headers={"X-Api-Key": settings.kyc_api_key},
            json={"selfie_ref": selfie_storage_key, "id_photo_ref": id_photo_storage_key},
        )
        resp.raise_for_status()
        return resp


async def verify_liveness_and_match(selfie_storage_key: str, id_photo_storage_key: str) -> dict:
    if settings.kyc_provider == "mock" or not settings.kyc_api_key:
        return {
            "_mode": "mock",
            "liveness_passed": True,
            "face_match_score": 0.97,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

    if settings.kyc_provider == "incode":
        resp = await _call_incode_liveness(selfie_storage_key, id_photo_storage_key)
        data = resp.json()
        data["_mode"] = "real"
        return data

    if settings.kyc_provider == "aws_rekognition":
        # import boto3
        # rekognition = boto3.client("rekognition", region_name=settings.aws_rekognition_region)
        # response = rekognition.compare_faces(
        #     SourceImage={"S3Object": {"Bucket": settings.s3_bucket, "Name": selfie_storage_key}},
        #     TargetImage={"S3Object": {"Bucket": settings.s3_bucket, "Name": id_photo_storage_key}},
        #     SimilarityThreshold=90,
        # )
        raise NotImplementedError(
            "Rekognition real pendiente de configurar boto3 + bucket con las imágenes. "
            "Ver comentario en verify_liveness_and_match()."
        )

    raise ValueError(f"kyc_provider desconocido: {settings.kyc_provider}")
