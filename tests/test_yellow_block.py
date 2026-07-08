import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.models.models import Client

client = TestClient(app)
ADMIN_HEADERS = {"X-Admin-Token": "change-me-admin-token"}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _create_client_and_key(plan="starter"):
    r = client.post(
        "/clients",
        headers=ADMIN_HEADERS,
        json={
            "company_name": "Fintech Demo SAC",
            "segment": "fintech",
            "contact_email": "ops@fintechdemo.pe",
            "plan": plan,
        },
    )
    client_id = r.json()["id"]
    r = client.post(f"/clients/{client_id}/api-keys?sandbox=true", headers=ADMIN_HEADERS)
    return client_id, r.json()["raw_key"]


def test_list_clients_requires_admin():
    r = client.get("/clients")
    assert r.status_code in (401, 422)


def test_list_clients_as_admin():
    _create_client_and_key()
    _create_client_and_key()
    r = client.get("/clients", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_signatures_scoped_to_own_client_only():
    _, key_a = _create_client_and_key()
    _, key_b = _create_client_and_key()

    client.post(
        "/signatures/sign",
        headers={"X-API-Key": key_a},
        json={
            "signer_name": "A", "signer_email": "a@x.com",
            "document_hash_sha256": "a" * 64, "signature_level": "simple",
        },
    )
    client.post(
        "/signatures/sign",
        headers={"X-API-Key": key_b},
        json={
            "signer_name": "B", "signer_email": "b@x.com",
            "document_hash_sha256": "b" * 64, "signature_level": "simple",
        },
    )

    r = client.get("/signatures", headers={"X-API-Key": key_a})
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"]  # es la firma de A, no ve la de B


def test_growth_plan_pricing_matches_landing_formula():
    """Replica la fórmula de updateCalc() del landing: base + excedente sobre 1000 ops."""
    _, key = _create_client_and_key(plan="growth")
    headers = {"X-API-Key": key}

    # 5 firmas + 3 KYC = 8 operaciones, muy por debajo de las 1000 incluidas
    for i in range(5):
        client.post(
            "/signatures/sign", headers=headers,
            json={
                "signer_name": f"S{i}", "signer_email": f"s{i}@x.com",
                "document_hash_sha256": str(i) * 64, "signature_level": "simple",
            },
        )
    for i in range(3):
        client.post(
            "/kyc/verify", headers=headers,
            json={
                "subject_full_name": f"K{i}", "subject_document_number": f"{i}"*8,
                "selfie_storage_key": "s", "document_photo_storage_key": "d",
            },
        )

    r = client.get("/usage/summary", headers=headers)
    body = r.json()
    assert body["signatures_count"] == 5
    assert body["kyc_count"] == 3
    # Sin excedente (8 < 1000 incluidas): debe cobrar solo la base S/399
    assert body["estimated_cost_pen"] == 399.0


def test_kyc_manual_review_does_not_break_request_even_without_webhook():
    """Sin NOTIFICATIONS_WEBHOOK_URL configurado, notify_ops no debe tumbar el request."""
    _, key = _create_client_and_key()
    headers = {"X-API-Key": key}
    r = client.post(
        "/kyc/verify", headers=headers,
        json={
            "subject_full_name": "sancionado",  # dispara AML flagged en modo mock
            "subject_document_number": "87654321",
            "selfie_storage_key": "s", "document_photo_storage_key": "d",
        },
    )
    assert r.status_code == 201
    assert r.json()["overall_status"] == "manual_review"
