from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- Clients ---
class ClientCreate(BaseModel):
    company_name: str
    segment: str
    contact_email: EmailStr
    plan: str = "starter"


class ClientOut(BaseModel):
    id: str
    company_name: str
    segment: str
    contact_email: EmailStr
    plan: str
    created_at: datetime

    class Config:
        from_attributes = True


class ApiKeyCreated(BaseModel):
    id: str
    raw_key: str = Field(description="Solo se muestra esta vez. Guárdala.")
    key_prefix: str
    is_sandbox: bool


# --- Signatures ---
class SignatureCreate(BaseModel):
    signer_name: str
    signer_email: EmailStr
    signer_document_number: str | None = None
    document_hash_sha256: str
    document_storage_key: str | None = Field(
        default=None, description="storage_key devuelto por POST /uploads/document"
    )
    signature_level: str = Field(default="simple", pattern="^(simple|digital_certificada)$")


class SignatureOut(BaseModel):
    id: str
    status: str
    signature_level: str
    psc_certificate_serial: str | None = None
    version: int
    parent_signature_id: str | None = None
    created_at: datetime
    signed_at: datetime | None = None

    class Config:
        from_attributes = True


class ReSignCreate(BaseModel):
    document_hash_sha256: str
    document_storage_key: str | None = None


class SignatureVerifyOut(BaseModel):
    valid: bool
    signature_level: str
    signed_at: datetime | None
    document_hash_sha256: str


# --- KYC ---
class KycCreate(BaseModel):
    subject_full_name: str
    subject_document_number: str
    subject_document_type: str = "DNI"
    selfie_storage_key: str
    document_photo_storage_key: str


class KycOut(BaseModel):
    id: str
    subject_document_number: str
    overall_status: str
    liveness_passed: bool | None
    face_match_score: float | None
    reniec_validated: bool | None
    aml_status: str | None
    created_at: datetime

    class Config:
        from_attributes = True


# --- Usage ---
class UsageSummaryOut(BaseModel):
    client_id: str
    period: str
    signatures_count: int
    kyc_count: int
    estimated_cost_usd: float
    estimated_cost_pen: float


# --- Pilot lead (reemplaza FormSubmit) ---
class PilotLeadCreate(BaseModel):
    empresa: str
    segmento: str
    email: EmailStr
    volumen_estimado: str | None = None
    consent_privacidad: bool = Field(
        description="Checkbox opt-in obligatorio por Ley N.º 29733"
    )
