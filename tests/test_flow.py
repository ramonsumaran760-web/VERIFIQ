import os

os.environ["DATABASE_URL"] = "sqlite:///./test_verifiq.db"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text
from sqlalchemy.orm import sessionmaker

from app.core.audit import verify_chain
from app.core.database import Base, engine
from app.main import app
from app.models.models import AuditLog

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Las migraciones de Alembic aplican estos triggers en real; en el test
    # los recreamos directo para no depender de correr Alembic en cada test.
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS audit_log_no_update
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log es append-only: UPDATE no permitido');
            END;
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log es append-only: DELETE no permitido');
            END;
            """
        )
    yield


ADMIN_HEADERS = {"X-Admin-Token": "change-me-admin-token"}


def _create_client_and_key():
    r = client.post(
        "/clients",
        headers=ADMIN_HEADERS,
        json={
            "company_name": "Fintech Demo SAC",
            "segment": "fintech",
            "contact_email": "ops@fintechdemo.pe",
            "plan": "starter",
        },
    )
    assert r.status_code == 201
    client_id = r.json()["id"]

    r = client.post(f"/clients/{client_id}/api-keys?sandbox=true", headers=ADMIN_HEADERS)
    assert r.status_code == 201
    raw_key = r.json()["raw_key"]
    return client_id, raw_key


def test_full_flow_and_audit_chain():
    client_id, raw_key = _create_client_and_key()
    headers = {"X-API-Key": raw_key}

    # Firma simple
    r = client.post(
        "/signatures/sign",
        headers=headers,
        json={
            "signer_name": "Juan Perez",
            "signer_email": "juan@example.com",
            "document_hash_sha256": "a" * 64,
            "signature_level": "simple",
        },
    )
    assert r.status_code == 201
    sig_id = r.json()["id"]

    r = client.get(f"/signatures/verify/{sig_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["valid"] is True

    # KYC
    r = client.post(
        "/kyc/verify",
        headers=headers,
        json={
            "subject_full_name": "Juan Perez",
            "subject_document_number": "12345678",
            "selfie_storage_key": "selfies/juan.jpg",
            "document_photo_storage_key": "dnis/juan.jpg",
        },
    )
    assert r.status_code == 201
    assert r.json()["overall_status"] == "approved"

    # Usage summary refleja ambos eventos
    r = client.get("/usage/summary", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["signatures_count"] == 1
    assert body["kyc_count"] == 1
    assert body["estimated_cost_usd"] == 1.80  # 0.55 + 1.25

    # Sin API key -> 401
    r = client.get("/usage/summary")
    assert r.status_code == 422 or r.status_code == 401  # header ausente


def test_audit_chain_detects_tampering():
    from app.core.database import SessionLocal

    client_id, raw_key = _create_client_and_key()
    headers = {"X-API-Key": raw_key}
    client.post(
        "/signatures/sign",
        headers=headers,
        json={
            "signer_name": "Ana Lopez",
            "signer_email": "ana@example.com",
            "document_hash_sha256": "b" * 64,
            "signature_level": "simple",
        },
    )

    db = SessionLocal()
    ok, _ = verify_chain(db)
    assert ok is True

    # Los triggers de la migración 0002 son la primera línea de defensa (bloquean
    # el UPDATE directo). Aquí los quitamos para probar la SEGUNDA línea de
    # defensa: aunque alguien con acceso root a la BD lograra editar una fila,
    # la cadena de hashes lo delata igual.
    db.execute(sa_text("DROP TRIGGER IF EXISTS audit_log_no_update"))
    db.commit()

    row = db.query(AuditLog).filter(AuditLog.action == "signature.sign").first()
    row.action = "signature.sign_TAMPERED"
    db.commit()

    ok, broken_id = verify_chain(db)
    assert ok is False
    assert broken_id == row.id
    db.close()


def test_audit_log_rejects_direct_delete():
    from sqlalchemy.exc import IntegrityError

    from app.core.database import SessionLocal

    client_id, raw_key = _create_client_and_key()
    headers = {"X-API-Key": raw_key}
    client.post(
        "/signatures/sign",
        headers=headers,
        json={
            "signer_name": "Carlos Ruiz",
            "signer_email": "carlos@example.com",
            "document_hash_sha256": "c" * 64,
            "signature_level": "simple",
        },
    )

    db = SessionLocal()
    row = db.query(AuditLog).first()
    with pytest.raises(IntegrityError):
        db.execute(
            AuditLog.__table__.delete().where(AuditLog.id == row.id)
        )
        db.commit()
    db.rollback()
    db.close()
