"""분석 작업 워커 (PostgreSQL 기반 큐).

영상 분석은 수십 초~수 분이 걸리므로 API 요청 안에서 처리하지 않고 analysis_jobs 로 넘긴다 (3.2).
실행: python -m app.worker

단계 순서 (5.1 → 5.7). 각 단계는 입력·출력이 정해져 있어 따로 개발·테스트할 수 있다.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.db import connect

log = logging.getLogger("worksense.worker")

STAGES = ["preprocess", "transcribe", "extract_steps", "match_public_data", "easy_text", "auto_check", "media_assets"]


def stage_preprocess(conn, media_id: int) -> None:
    """5.1 원본 → audio.wav → part_NNN.wav (app.pipeline.media)."""
    raise NotImplementedError


def stage_transcribe(conn, media_id: int) -> None:
    """5.2 gemini-3.5-transcribe, 단어 타임스탬프 → transcripts. 조각 오프셋(n×1500초)을 더한다."""
    raise NotImplementedError


def stage_extract_steps(conn, media_id: int) -> None:
    """5.3 gemini-3.8-flash + 영상(File API) + [MM:SS] 전사문 → StepExtraction → tasks/steps."""
    raise NotImplementedError


def stage_match_public_data(conn, media_id: int) -> None:
    """5.4 함수 호출(MATCH_FUNCTIONS) → 구조화 출력(MatchResult) → step_refs, step_checks(ncs_gap/jobcode_gap)."""
    raise NotImplementedError


def stage_easy_text(conn, media_id: int) -> None:
    """5.5 gemini-3.5-flash-lite 로 '한 문장 하나의 행동' 안내문(EasyText)."""
    raise NotImplementedError


def stage_auto_check(conn, media_id: int) -> None:
    """5.6 app.pipeline.easy_text_check → step_checks."""
    raise NotImplementedError


def stage_media_assets(conn, media_id: int) -> None:
    """5.7 대표 사진(구간 중앙)·5~10초 안내 클립 → steps.photo_path/clip_path."""
    raise NotImplementedError


HANDLERS: dict[str, Callable] = {
    "preprocess": stage_preprocess,
    "transcribe": stage_transcribe,
    "extract_steps": stage_extract_steps,
    "match_public_data": stage_match_public_data,
    "easy_text": stage_easy_text,
    "auto_check": stage_auto_check,
    "media_assets": stage_media_assets,
}


def claim_job(conn) -> dict | None:
    return conn.execute(
        """
        UPDATE analysis_jobs SET status = 'running', started_at = now()
        WHERE id = (
          SELECT id FROM analysis_jobs WHERE status = 'queued'
          ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
        )
        RETURNING id, media_id, stage
        """
    ).fetchone()


def enqueue_next(conn, media_id: int, stage: str) -> None:
    i = STAGES.index(stage)
    if i + 1 < len(STAGES):
        conn.execute("INSERT INTO analysis_jobs (media_id, stage, status) VALUES (%s, %s, 'queued')",
                     (media_id, STAGES[i + 1]))


def run_once() -> bool:
    with connect() as conn:
        job = claim_job(conn)
        conn.commit()
        if job is None:
            return False
        try:
            HANDLERS[job["stage"]](conn, job["media_id"])
            conn.execute("UPDATE analysis_jobs SET status='done', finished_at=now() WHERE id=%s", (job["id"],))
            enqueue_next(conn, job["media_id"], job["stage"])
            conn.commit()
        except Exception as e:
            conn.rollback()
            log.exception("job %s failed", job["id"])
            conn.execute("UPDATE analysis_jobs SET status='failed', error=%s, finished_at=now() WHERE id=%s",
                         (repr(e)[:2000], job["id"]))
            conn.commit()
        return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    log.info("worker started")
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
