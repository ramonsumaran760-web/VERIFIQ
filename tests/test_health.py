from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_landing_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "VerifiQ" in resp.text
    assert "window.location.origin" in resp.text


def test_favicon_does_not_404():
    resp = client.get("/favicon.ico")
    assert resp.status_code == 204
