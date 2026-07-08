import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, Boolean, ForeignKey, Text, Float, Integer, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


class Client(Base):
    __tablename__ = "clients"

    id = Column(String, primary_key=True, default=uuid_str)
    company_name = Column(String, nullable=False)
    segment = Column(String, nullable=False)  # fintech | coopac | inmobiliaria | otro
    contact_email = Column(String, nullable=False)
    plan = Column(String, default="starter")  # starter | growth | enterprise
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    api_keys = relationship("ApiKey", back_populates="client")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(String, primary_key=True, default=uuid_str)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    key_hash = Column(String, nullable=False, unique=True)  # SHA-256, nunca en claro
    key_prefix = Column(String, nullable=False)  # primeros 12 chars, solo para mostrar en UI
    label = Column(String, default="default")
    is_sandbox = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)

    client = relationship("Client", back_populates="api_keys")


class SignatureRequest(Base):
    __tablename__ = "signature_requests"

    id = Column(String, primary_key=True, default=uuid_str)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    signer_name = Column(String, nullable=False)
    signer_email = Column(String, nullable=False)
    signer_document_number = Column(String, nullable=True)  # DNI/RUC si aplica
    document_hash_sha256 = Column(String, nullable=False)  # hash del PDF original
    signature_level = Column(String, nullable=False)  # simple | digital_certificada
    psc_provider = Column(String, nullable=True)  # quién certificó, si fue digital
    psc_certificate_serial = Column(String, nullable=True)
    padres_applied = Column(Boolean, default=False)
    timestamp_token = Column(Text, nullable=True)  # sello de tiempo RFC 3161, si aplica
    signed_document_storage_key = Column(String, nullable=True)  # ubicación en storage cifrado
    status = Column(String, default="pending")  # pending | signed | verified | revoked
    signer_ip = Column(String, nullable=True)
    signer_user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    signed_at = Column(DateTime, nullable=True)

    # Versionado: si un documento se vuelve a firmar (corrección, adenda, etc.)
    # se crea una NUEVA fila en vez de sobreescribir la firma anterior — la
    # firma original tiene que seguir siendo consultable tal cual quedó.
    version = Column(Integer, default=1, nullable=False)
    parent_signature_id = Column(String, ForeignKey("signature_requests.id"), nullable=True)


class KycVerification(Base):
    __tablename__ = "kyc_verifications"

    id = Column(String, primary_key=True, default=uuid_str)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    subject_document_number = Column(String, nullable=False)  # DNI o RUC
    subject_document_type = Column(String, default="DNI")
    liveness_passed = Column(Boolean, nullable=True)
    face_match_score = Column(Float, nullable=True)  # 0-1
    reniec_validated = Column(Boolean, nullable=True)
    reniec_full_name_match = Column(Boolean, nullable=True)
    sunat_validated = Column(Boolean, nullable=True)
    aml_status = Column(String, nullable=True)  # clear | flagged | pending
    aml_match_details = Column(JSON, nullable=True)
    selfie_storage_key = Column(String, nullable=True)  # storage cifrado, no en la fila
    document_photo_storage_key = Column(String, nullable=True)
    overall_status = Column(String, default="pending")  # pending | approved | manual_review | rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    """
    Append-only. Nunca se hace UPDATE ni DELETE sobre esta tabla desde código
    de aplicación — se refuerza también a nivel de base de datos con una regla
    (ver migración 0002) que bloquea updates/deletes.
    """
    __tablename__ = "audit_log"

    id = Column(String, primary_key=True, default=uuid_str)
    client_id = Column(String, ForeignKey("clients.id"), nullable=True)
    actor = Column(String, nullable=False)  # api_key_id, "system", o email de usuario humano
    action = Column(String, nullable=False)  # ej: signature.sign, kyc.verify, apikey.create
    resource_type = Column(String, nullable=False)
    resource_id = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    prev_hash = Column(String, nullable=False)
    event_hash = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id = Column(String, primary_key=True, default=uuid_str)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    event_type = Column(String, nullable=False)  # signature | kyc
    unit_cost_usd = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=uuid_str)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    provider = Column(String, nullable=False)  # culqi | kushki | mercadopago
    provider_charge_id = Column(String, nullable=True)
    amount_pen = Column(Float, nullable=False)
    status = Column(String, default="pending")  # pending | paid | failed | refunded
    plan = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PilotLead(Base):
    """Reemplaza a FormSubmit.co — el formulario del landing pega directo aquí."""
    __tablename__ = "pilot_leads"

    id = Column(String, primary_key=True, default=uuid_str)
    empresa = Column(String, nullable=False)
    segmento = Column(String, nullable=False)
    email = Column(String, nullable=False)
    volumen_estimado = Column(String, nullable=True)
    consent_privacidad = Column(Boolean, default=False)  # opt-in Ley 29733
    source_ip = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    contacted = Column(Boolean, default=False)


class IdempotencyKey(Base):
    """
    Evita que un reintento de red (timeout del cliente, doble-click, etc.)
    genere una firma o un cobro duplicado. El cliente manda un header
    `Idempotency-Key`; si ya se vio esa combinación (cliente + endpoint + key),
    se devuelve la respuesta guardada en vez de re-ejecutar la operación.
    """
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("client_id", "endpoint", "idempotency_key", name="uq_idempotency_scope"),
    )

    id = Column(String, primary_key=True, default=uuid_str)
    client_id = Column(String, ForeignKey("clients.id"), nullable=False)
    endpoint = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
