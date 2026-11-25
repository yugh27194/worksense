"""담당자 API (인계서 7장). 인증은 미구현 — MVP 개발 중에는 X-Workplace-Id 헤더로 사업장을 지정한다.

모든 조회는 workplace_id 조건을 강제한다 (6장, 사업장 간 데이터 분리).
"""
from __future__ import annotations

import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.db import get_conn

router = APIRouter(tags=["staff"])


def workplace_id(x_workplace_id: int = Header(...)) -> int:
    # TODO: 담당자 로그인으로 교체
    return x_workplace_id


@router.post("/media")
def upload_media(
    kind: str = Form(...),
    title: str = Form(""),
    consent_confirmed: bool = Form(...),
    file: UploadFile = File(...),
    wp: int = Depends(workplace_id),
    conn=Depends(get_conn),
):
    """영상·문서 업로드. 촬영 동의 확인 체크 필수 (4.7)."""
    if not consent_confirmed:
        raise HTTPException(400, "촬영·이용 동의 확인이 필요합니다")
    if kind not in ("workplace_video", "document", "photo"):
        raise HTTPException(400, "kind 값이 올바르지 않습니다")
    root: Path = get_settings().storage_dir / f"wp{wp}" / "media"
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{secrets.token_hex(8)}_{Path(file.filename or 'upload').name}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    row = conn.execute(
        "INSERT INTO source_media (workplace_id, kind, title, storage_path, consent_confirmed) "
        "VALUES (%s, %s, %s, %s, true) RETURNING id",
        (wp, kind, title, str(dest)),
    ).fetchone()
    conn.commit()
    return {"id": row["id"]}


@router.post("/media/{media_id}/analyze")
def analyze(media_id: int, wp: int = Depends(workplace_id), conn=Depends(get_conn)):
    """5.1~5.7 분석 작업 등록. 첫 단계(preprocess)만 넣으면 워커가 다음 단계를 이어서 넣는다."""
    m = conn.execute("SELECT id FROM source_media WHERE id=%s AND workplace_id=%s", (media_id, wp)).fetchone()
    if m is None:
        raise HTTPException(404)
    job = conn.execute(
        "INSERT INTO analysis_jobs (media_id, stage, status) VALUES (%s, 'preprocess', 'queued') RETURNING id",
        (media_id,),
    ).fetchone()
    conn.commit()
    return {"job_id": job["id"]}


@router.get("/jobs/{media_id}")
def job_status(media_id: int, wp: int = Depends(workplace_id), conn=Depends(get_conn)):
    """분석 진행 상태: 단계별 작업 목록."""
    rows = conn.execute(
        "SELECT j.stage, j.status, j.error, j.started_at, j.finished_at FROM analysis_jobs j "
        "JOIN source_media m ON m.id = j.media_id WHERE j.media_id=%s AND m.workplace_id=%s ORDER BY j.id",
        (media_id, wp),
    ).fetchall()
    return {"media_id": media_id, "stages": rows}


@router.get("/manuals/{manual_id}")
def get_manual(manual_id: int, wp: int = Depends(workplace_id), conn=Depends(get_conn)):
    """업무·단계·점검 결과 조회."""
    manual = conn.execute("SELECT * FROM manuals WHERE id=%s AND workplace_id=%s", (manual_id, wp)).fetchone()
    if manual is None:
        raise HTTPException(404)
    tasks = conn.execute("SELECT * FROM tasks WHERE manual_id=%s ORDER BY sort_order", (manual_id,)).fetchall()
    for t in tasks:
        t["steps"] = conn.execute("SELECT * FROM steps WHERE task_id=%s ORDER BY sort_order", (t["id"],)).fetchall()
        for s in t["steps"]:
            s["checks"] = conn.execute(
                "SELECT id, check_type, payload, resolved FROM step_checks WHERE step_id=%s", (s["id"],)
            ).fetchall()
    return {**manual, "tasks": tasks}


class StepPatch(BaseModel):
    easy_text: str | None = None
    caution_text: str | None = None
    tools: list[str] | None = None
    location: str | None = None


@router.patch("/steps/{step_id}")
def patch_step(step_id: int, body: StepPatch, wp: int = Depends(workplace_id), conn=Depends(get_conn)):
    """단계 수정. 수정 이력은 step_revisions 에 자동 저장 (5.8)."""
    raise HTTPException(501, "TODO: steps 갱신 + step_revisions(source='staff') 기록, status='in_review'")


@router.post("/steps/{step_id}/media")
def replace_step_media(step_id: int, wp: int = Depends(workplace_id)):
    """사진·클립 교체, 위치 표시 저장 (위치 표시 방식은 12장 #3 미결)."""
    raise HTTPException(501, "TODO")


@router.post("/steps/{step_id}/approve")
def approve_step(step_id: int, wp: int = Depends(workplace_id)):
    """승인 → status='approved', approved_by/at 기록, 5.9 임베딩 실행."""
    raise HTTPException(501, "TODO")


@router.get("/improvements")
def list_improvements(wp: int = Depends(workplace_id)):
    """반복 질문 묶음·근거 없는 질문 (5.11)."""
    raise HTTPException(501, "TODO")


@router.post("/improvements/{item_id}/approve")
def approve_improvement(item_id: int, wp: int = Depends(workplace_id)):
    """보완 설명 승인 → 단계 새 버전 + 재임베딩."""
    raise HTTPException(501, "TODO")


@router.post("/workplaces/{wid}/qr")
def issue_qr(wid: int, wp: int = Depends(workplace_id), conn=Depends(get_conn)):
    """근로자 접속 QR 발급. 근로자 식별 정보는 저장하지 않는다."""
    if wid != wp:
        raise HTTPException(403)
    token = secrets.token_urlsafe(16)
    conn.execute("INSERT INTO worker_sessions (workplace_id, qr_token) VALUES (%s, %s)", (wid, token))
    conn.commit()
    return {"qr_token": token, "path": f"/w/{token}"}


@router.get("/help/calls")
def help_calls(wp: int = Depends(workplace_id), conn=Depends(get_conn)):
    """'사람 불러줘' 최근 호출 목록 (어느 업무·단계에서). 근로자는 식별하지 않는다."""
    return conn.execute(
        """
        SELECT h.id, h.created_at, t.name AS task_name, st.sort_order, st.easy_text
        FROM help_events h JOIN steps st ON st.id = h.step_id JOIN tasks t ON t.id = st.task_id
        WHERE h.workplace_id = %s AND h.kind = 'handoff' AND h.created_at > now() - interval '1 day'
        ORDER BY h.created_at DESC LIMIT 20
        """,
        (wp,),
    ).fetchall()


@router.get("/help/stats")
def help_stats(wp: int = Depends(workplace_id), conn=Depends(get_conn)):
    """단계별 도움 요청 합계 → 설명이 부족한 단계 찾기 (5.11). 개인별 통계는 만들지 않는다."""
    return conn.execute(
        """
        SELECT st.id AS step_id, t.name AS task_name, st.sort_order, st.easy_text,
               count(*) FILTER (WHERE h.kind = 'repeat') AS repeat,
               count(*) FILTER (WHERE h.kind = 'easier') AS easier,
               count(*) FILTER (WHERE h.kind = 'photo') AS photo,
               count(*) FILTER (WHERE h.kind = 'handoff') AS handoff
        FROM help_events h JOIN steps st ON st.id = h.step_id JOIN tasks t ON t.id = st.task_id
        WHERE h.workplace_id = %s
        GROUP BY st.id, t.name, st.sort_order, st.easy_text
        ORDER BY count(*) DESC
        """,
        (wp,),
    ).fetchall()
