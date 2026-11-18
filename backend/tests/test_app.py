from fastapi.testclient import TestClient

from app.main import app


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_routes_registered():
    paths = set(app.openapi()["paths"])
    for p in ["/media", "/media/{media_id}/analyze", "/manuals/{manual_id}", "/steps/{step_id}/approve",
              "/w/{qr_token}", "/w/ask", "/internal/ingest/{source}"]:
        assert p in paths
