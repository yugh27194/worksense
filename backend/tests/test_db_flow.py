"""DB 통합 테스트. TEST_DATABASE_URL 이 있을 때만 실행 (CI 는 pgvector 서비스 컨테이너로 실행)."""
import os

import pytest

DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB, reason="TEST_DATABASE_URL 없음")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    from app import config, db

    config.get_settings.cache_clear()
    db._pool = None
    from fastapi.testclient import TestClient

    from app.main import app

    with db.connect() as conn:
        wid = conn.execute("INSERT INTO workplaces (name) VALUES ('시범 카페') RETURNING id").fetchone()["id"]
        conn.commit()
    yield TestClient(app), wid


def test_upload_analyze_and_queue(client):
    from app import worker

    c, wid = client
    h = {"X-Workplace-Id": str(wid)}
    r = c.post("/media", headers=h, data={"kind": "workplace_video", "consent_confirmed": "false"},
               files={"file": ("a.mp4", b"x")})
    assert r.status_code == 400  # 동의 확인 없으면 거부
    r = c.post("/media", headers=h, data={"kind": "workplace_video", "consent_confirmed": "true", "title": "오픈"},
               files={"file": ("a.mp4", b"x")})
    media_id = r.json()["id"]
    assert c.post(f"/media/{media_id}/analyze", headers=h).status_code == 200
    assert c.post(f"/media/{media_id}/analyze", headers={"X-Workplace-Id": str(wid + 999)}).status_code == 404

    assert worker.run_once() is True  # preprocess 는 아직 미구현 → failed 로 기록
    stages = c.get(f"/jobs/{media_id}", headers=h).json()["stages"]
    assert stages[0]["stage"] == "preprocess" and stages[0]["status"] == "failed"


def test_qr_session(client):
    c, wid = client
    tok = c.post(f"/workplaces/{wid}/qr", headers={"X-Workplace-Id": str(wid)}).json()["qr_token"]
    assert c.get(f"/w/{tok}").json()["workplace_id"] == wid
    assert c.get("/w/manuals", headers={"X-Worker-Token": tok}).json() == []
    assert c.put("/w/session/preferences", headers={"X-Worker-Token": tok},
                 json={"answers": {"q1": "사진 먼저"}}).json() == {"ok": True}
