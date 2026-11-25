"""근로자 API (인계서 7장, /w 접두사). QR 토큰으로 세션을 식별하며 승인된 단계만 보여 준다."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.db import get_conn

router = APIRouter(prefix="/w", tags=["worker"])


def session(x_worker_token: str = Header(...), conn=Depends(get_conn)) -> dict:
    s = conn.execute("SELECT id, workplace_id, preferences FROM worker_sessions WHERE qr_token=%s",
                     (x_worker_token,)).fetchone()
    if s is None:
        raise HTTPException(401)
    return s


class Preferences(BaseModel):
    # 3~4개 선택 질문 문항은 미결 (12장 #1). 자유 형식 dict 로 받는다.
    answers: dict[str, str]


@router.put("/session/preferences")
def save_preferences(body: Preferences, s=Depends(session), conn=Depends(get_conn)):
    from psycopg.types.json import Jsonb

    conn.execute("UPDATE worker_sessions SET preferences=%s WHERE id=%s", (Jsonb(body.answers), s["id"]))
    conn.commit()
    return {"ok": True}


@router.get("/manuals")
def manuals(s=Depends(session), conn=Depends(get_conn)):
    """승인된 단계가 하나라도 있는 업무 목록."""
    return conn.execute(
        """
        SELECT DISTINCT m.id AS manual_id, m.job_name, t.id AS task_id, t.name AS task_name, t.sort_order
        FROM manuals m JOIN tasks t ON t.manual_id = m.id JOIN steps st ON st.task_id = t.id
        WHERE m.workplace_id = %s AND st.status = 'approved'
        ORDER BY m.id, t.sort_order
        """,
        (s["workplace_id"],),
    ).fetchall()


@router.get("/tasks/{task_id}")
def task_cards(task_id: int, s=Depends(session), conn=Depends(get_conn)):
    """승인된 단계 카드: 행동 문장, 대표 사진, 5~10초 영상, 주의 사항."""
    return conn.execute(
        """
        SELECT st.id, st.sort_order, st.easy_text, st.easier_text, st.caution_text, st.tools,
               st.photo_path, st.clip_path, st.location_markup, st.ai_generated, st.approved_at
        FROM steps st JOIN tasks t ON t.id = st.task_id JOIN manuals m ON m.id = t.manual_id
        WHERE t.id = %s AND m.workplace_id = %s AND st.status = 'approved'
        ORDER BY st.sort_order
        """,
        (task_id, s["workplace_id"]),
    ).fetchall()


class Help(BaseModel):
    step_id: int
    kind: Literal["repeat", "easier", "photo", "handoff", "done"]


@router.post("/help")
def help_button(body: Help, s=Depends(session), conn=Depends(get_conn)):
    """버튼형 도움 기록 (제안서 6장 2). 근로자 세션은 저장하지 않고 단계별 합계로만 쓴다.
    '사람 불러줘'(handoff)는 담당자 화면의 호출 목록에 뜬다 (연결 채널은 12장 #4 미결)."""
    ok = conn.execute(
        "SELECT 1 FROM steps st JOIN tasks t ON t.id = st.task_id JOIN manuals m ON m.id = t.manual_id "
        "WHERE st.id = %s AND m.workplace_id = %s AND st.status = 'approved'",
        (body.step_id, s["workplace_id"]),
    ).fetchone()
    if ok is None:
        raise HTTPException(404)
    conn.execute("INSERT INTO help_events (workplace_id, step_id, kind) VALUES (%s, %s, %s)",
                 (s["workplace_id"], body.step_id, body.kind))
    conn.commit()
    return {"ok": True}


class Ask(BaseModel):
    question: str


@router.post("/ask")
def ask(body: Ask, s=Depends(session)):
    """질문 → 임베딩 → workplace_id·approved 로 거른 top-k 검색 → 임계값 미만이면 담당자 연결 →
    Flash-Lite 답변 → qa.validate_answer 로 근거 검증 → question_logs 저장 (5.10)."""
    raise HTTPException(501, "TODO")


@router.post("/ask/{question_id}/more-help")
def more_help(question_id: int, s=Depends(session)):
    """단계적 도움 다음 단계 (qa.HELP_LEVELS)."""
    raise HTTPException(501, "TODO")


@router.post("/handoff")
def handoff(s=Depends(session)):
    """담당자 연결 요청. 연결 채널은 미결 (12장 #4)."""
    raise HTTPException(501, "TODO")


@router.get("/welfare")
def welfare(ctpv: str | None = None, sgg: str | None = None, theme: str | None = None, s=Depends(session)):
    """복지서비스 안내 (P1, 12장 #6). 수급 자격은 판정하지 않고 원문 링크·문의처를 함께 보여 준다."""
    raise HTTPException(501, "TODO")


# /w/manuals 등 고정 경로보다 뒤에 둬야 경로 충돌이 없다.
@router.get("/{qr_token}")
def start(qr_token: str, conn=Depends(get_conn)):
    """세션 시작: QR 진입."""
    s = conn.execute("SELECT workplace_id, preferences FROM worker_sessions WHERE qr_token=%s",
                     (qr_token,)).fetchone()
    if s is None:
        raise HTTPException(404)
    return s
