import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app
from app.core.retry import with_provider_retry

client = TestClient(app)
ADMIN_HEADERS = {"X-Admin-Token": "change-me-admin-token"}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
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


# --- Rate limiting ---

def test_pilot_leads_rate_limit_kicks_in_after_5_per_minute():
    payload = {
        "empresa": "X", "segmento": "fintech", "email": "a@b.com",
        "consent_privacidad": True,
    }
    statuses = [client.post("/pilot-leads", json=payload).status_code for _ in range(7)]
    assert statuses[:5] == [201] * 5
    assert 429 in statuses[5:]


def test_signature_sign_rate_limit_is_per_client_not_global():
    """Dos clientes distintos no deberían compartir el mismo balde de rate limit."""
    _, key_a = _create_client_and_key()
    _, key_b = _create_client_and_key()

    payload = {
        "signer_name": "A", "signer_email": "a@x.com",
        "document_hash_sha256": "a" * 64, "signature_level": "simple",
    }
    # Agotamos parte del límite de A
    for _ in range(3):
        r = client.post("/signatures/sign", headers={"X-API-Key": key_a}, json=payload)
        assert r.status_code == 201

    # B no debería verse afectado por el consumo de A
    r = client.post("/signatures/sign", headers={"X-API-Key": key_b}, json=payload)
    assert r.status_code == 201


# --- Retry con backoff ante errores transitorios ---

@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure():
    attempts = {"count": 0}

    @with_provider_retry
    async def flaky_call():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise httpx.ConnectError("conexión perdida", request=httpx.Request("GET", "http://x"))
        return "ok"

    result = await flaky_call()
    assert result == "ok"
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_retry_gives_up_after_max_attempts():
    attempts = {"count": 0}

    @with_provider_retry
    async def always_fails():
        attempts["count"] += 1
        raise httpx.ConnectError("caído", request=httpx.Request("GET", "http://x"))

    with pytest.raises(httpx.ConnectError):
        await always_fails()
    assert attempts["count"] == 3  # stop_after_attempt(3)


@pytest.mark.asyncio
async def test_retry_does_not_retry_4xx_client_errors():
    attempts = {"count": 0}

    @with_provider_retry
    async def bad_request():
        attempts["count"] += 1
        request = httpx.Request("GET", "http://x")
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    with pytest.raises(httpx.HTTPStatusError):
        await bad_request()
    assert attempts["count"] == 1  # no reintenta errores 4xx


# --- Versionado de firmas ---

def test_re_sign_creates_new_version_without_touching_original():
    _, key = _create_client_and_key()
    headers = {"X-API-Key": key}

    r = client.post(
        "/signatures/sign", headers=headers,
        json={
            "signer_name": "Juan Perez", "signer_email": "juan@x.com",
            "document_hash_sha256": "a" * 64, "signature_level": "simple",
        },
    )
    original_id = r.json()["id"]
    assert r.json()["version"] == 1

    r2 = client.post(
        f"/signatures/{original_id}/re-sign", headers=headers,
        json={"document_hash_sha256": "b" * 64},
    )
    assert r2.status_code == 201
    assert r2.json()["version"] == 2
    assert r2.json()["parent_signature_id"] == original_id
    assert r2.json()["id"] != original_id

    # La original sigue intacta
    r3 = client.get(f"/signatures/verify/{original_id}", headers=headers)
    assert r3.json()["document_hash_sha256"] == "a" * 64

    # El historial de versiones trae ambas, en orden
    r4 = client.get(f"/signatures/{original_id}/versions", headers=headers)
    versions = r4.json()
    assert [v["version"] for v in versions] == [1, 2]


# --- Tipo de cambio con fallback ---

@pytest.mark.asyncio
async def test_exchange_rate_falls_back_when_provider_is_down():
    from app.adapters import exchange_rate_adapter

    exchange_rate_adapter._cache["rate"] = None
    exchange_rate_adapter._cache["fetched_at"] = 0.0

    with respx.mock:
        respx.get("https://api.exchangerate-api.com/v4/latest/USD").mock(
            side_effect=httpx.ConnectError("sin red")
        )
        rate = await exchange_rate_adapter.get_usd_to_pen_rate()
    assert rate == exchange_rate_adapter.FALLBACK_RATE_PEN
