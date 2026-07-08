import io

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app

client = TestClient(app)

ADMIN_HEADERS = {"X-Admin-Token": "change-me-admin-token"}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log "
            "BEGIN SELECT RAISE(ABORT, 'no update'); END;"
        )
        conn.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log "
            "BEGIN SELECT RAISE(ABORT, 'no delete'); END;"
        )
    yield


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
    client_id = r.json()["id"]
    r = client.post(f"/clients/{client_id}/api-keys?sandbox=true", headers=ADMIN_HEADERS)
    return client_id, r.json()["raw_key"]


# --- Admin auth ---

def test_create_client_without_admin_token_is_rejected():
    r = client.post(
        "/clients",
        json={"company_name": "X", "segment": "fintech", "contact_email": "a@b.com"},
    )
    assert r.status_code in (401, 422)  # 422 si falta el header, 401 si es incorrecto


def test_create_client_with_wrong_admin_token_is_rejected():
    r = client.post(
        "/clients",
        headers={"X-Admin-Token": "wrong-token"},
        json={"company_name": "X", "segment": "fintech", "contact_email": "a@b.com"},
    )
    assert r.status_code == 401


def test_create_client_with_correct_admin_token_works():
    r = client.post(
        "/clients",
        headers=ADMIN_HEADERS,
        json={"company_name": "X", "segment": "fintech", "contact_email": "a@b.com"},
    )
    assert r.status_code == 201


# --- File uploads wired to storage + signature flow ---

def test_upload_document_and_sign_with_real_hash():
    _, raw_key = _create_client_and_key()
    headers = {"X-API-Key": raw_key}

    fake_pdf = b"%PDF-1.4 contenido de prueba"
    r = client.post(
        "/uploads/document",
        headers=headers,
        files={"file": ("contrato.pdf", io.BytesIO(fake_pdf), "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert "storage_key" in body
    assert len(body["document_hash_sha256"]) == 64

    # El hash devuelto por el upload es el que se usa para firmar, no uno inventado
    r = client.post(
        "/signatures/sign",
        headers=headers,
        json={
            "signer_name": "Juan Perez",
            "signer_email": "juan@example.com",
            "document_hash_sha256": body["document_hash_sha256"],
            "document_storage_key": body["storage_key"],
            "signature_level": "simple",
        },
    )
    assert r.status_code == 201


def test_upload_rejects_wrong_content_type():
    _, raw_key = _create_client_and_key()
    headers = {"X-API-Key": raw_key}
    r = client.post(
        "/uploads/document",
        headers=headers,
        files={"file": ("foto.png", io.BytesIO(b"fake"), "image/png")},
    )
    assert r.status_code == 400


def test_upload_requires_client_api_key():
    fake_pdf = b"%PDF-1.4 sin api key"
    r = client.post(
        "/uploads/document",
        files={"file": ("contrato.pdf", io.BytesIO(fake_pdf), "application/pdf")},
    )
    assert r.status_code in (401, 422)


# --- Idempotency ---

def test_idempotent_signature_does_not_double_charge():
    _, raw_key = _create_client_and_key()
    headers = {"X-API-Key": raw_key, "Idempotency-Key": "retry-abc-123"}
    payload = {
        "signer_name": "Ana Lopez",
        "signer_email": "ana@example.com",
        "document_hash_sha256": "d" * 64,
        "signature_level": "simple",
    }

    r1 = client.post("/signatures/sign", headers=headers, json=payload)
    assert r1.status_code == 201
    sig_id_1 = r1.json()["id"]

    # Reintento con la misma key: debe devolver la MISMA firma, no crear otra
    r2 = client.post("/signatures/sign", headers=headers, json=payload)
    assert r2.status_code == 201
    assert r2.json()["id"] == sig_id_1

    # Y el usage no debe haberse duplicado
    r = client.get("/usage/summary", headers={"X-API-Key": raw_key})
    assert r.json()["signatures_count"] == 1
    assert r.json()["estimated_cost_usd"] == 0.55


def test_different_idempotency_keys_create_separate_signatures():
    _, raw_key = _create_client_and_key()
    payload = {
        "signer_name": "Carlos Ruiz",
        "signer_email": "carlos@example.com",
        "document_hash_sha256": "e" * 64,
        "signature_level": "simple",
    }
    r1 = client.post(
        "/signatures/sign",
        headers={"X-API-Key": raw_key, "Idempotency-Key": "key-1"},
        json=payload,
    )
    r2 = client.post(
        "/signatures/sign",
        headers={"X-API-Key": raw_key, "Idempotency-Key": "key-2"},
        json=payload,
    )
    assert r1.json()["id"] != r2.json()["id"]
