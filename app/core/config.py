"""
Configuración centralizada. TODAS las credenciales de terceros viven en variables
de entorno (ver .env.example) — nunca hardcodeadas en el código.

Si una variable requerida para un adapter en modo "real" no está seteada,
el adapter cae a modo mock y lo deja explícito en los logs y en la respuesta
(campo `_mode`), para que nunca se confunda un resultado simulado con uno real.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ---
    app_name: str = "VerifiQ API"
    environment: str = "development"  # development | staging | production
    secret_key: str = "change-me-in-production"
    admin_api_token: str = "change-me-admin-token"
    database_url: str = "sqlite:///./verifiq.db"
    cors_allowed_origins: str = "http://localhost:3000"  # coma-separado
    notifications_webhook_url: str | None = None  # Slack/Discord incoming webhook
    sentry_dsn: str | None = None
    log_level: str = "INFO"

    # --- PSC / PAdES (firma digital certificada) ---
    psc_provider: str = "mock"  # mock | camerfirma | iodigital
    psc_api_base_url: str | None = None
    psc_api_key: str | None = None
    psc_tsa_url: str = "http://timestamp.digicert.com"  # sello de tiempo RFC 3161

    # --- KYC biométrico ---
    kyc_provider: str = "mock"  # mock | incode | aws_rekognition | faceio
    kyc_api_base_url: str | None = None
    kyc_api_key: str | None = None
    aws_rekognition_region: str | None = None

    # --- RENIEC / SUNAT ---
    reniec_api_base_url: str | None = None
    reniec_api_token: str | None = None
    sunat_api_base_url: str | None = None
    sunat_api_token: str | None = None

    # --- AML / listas de sanciones ---
    aml_provider: str = "mock"  # mock | complyadvantage
    aml_api_base_url: str | None = None
    aml_api_key: str | None = None

    # --- Storage cifrado (documentos firmados, DNIs) ---
    storage_backend: str = "local"  # local | s3
    s3_bucket: str | None = None
    s3_kms_key_id: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"

    # --- Pasarela de pagos ---
    payments_provider: str = "mock"  # mock | culqi | kushki | mercadopago
    payments_secret_key: str | None = None
    payments_public_key: str | None = None
    payments_webhook_secret: str | None = None

    # --- API keys de clientes (hashing) ---
    api_key_hash_algo: str = "sha256"


@lru_cache
def get_settings() -> Settings:
    return Settings()
