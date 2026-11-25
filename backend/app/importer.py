"""검수 끝난 검토표(data/review/<job>/steps_review.csv)를 DB 에 반영한다 (인계서 5.8).

- decision 이 approve·edit 인 단계만 status='approved' 로 넣는다. 나머지는 'in_review' (근로자에게 안 보임).
- edit 이면 edited_easy_text 를 안내문으로 쓰고, 원본 설명 → AI 안내문 → 담당자 수정본을 step_revisions 에 남긴다.
- 같은 직무를 다시 넣으면 그 매뉴얼을 지우고 새로 만든다 (프로토타입 단순화).
"""
from __future__ import annotations

import os

from psycopg.types.json import Jsonb

from app.batch import DATA, read_csv, review_dir
from app.db import connect
from app.pipeline import media

DEMO_WORKPLACE = os.environ.get("DEMO_WORKPLACE_NAME", "시연 사업장")


def _ms(v: str) -> int | None:
    try:
        return media.mmss_to_ms(v)
    except (ValueError, AttributeError):
        return None


def ensure_workplace(conn, name: str = DEMO_WORKPLACE) -> int:
    row = conn.execute("SELECT id FROM workplaces WHERE name=%s ORDER BY id LIMIT 1", (name,)).fetchone()
    if row:
        return row["id"]
    return conn.execute("INSERT INTO workplaces (name) VALUES (%s) RETURNING id", (name,)).fetchone()["id"]


def import_job(job: str) -> dict:
    jobs = {r["job_key"]: r for r in read_csv(DATA / "curated/jobs.csv")}
    if job not in jobs:
        raise SystemExit(f"jobs.csv 에 '{job}' 없음")
    rows = sorted(read_csv(review_dir(job) / "steps_review.csv"), key=lambda r: int(r["order"]))
    if not rows:
        raise SystemExit("검토표가 없습니다. python -m app.batch all 먼저 실행")

    with connect() as conn:
        wp = ensure_workplace(conn)
        old = conn.execute("SELECT id FROM manuals WHERE workplace_id=%s AND source_job_key=%s", (wp, job)).fetchall()
        for m in old:
            _delete_manual(conn, m["id"])
        manual_id = conn.execute(
            "INSERT INTO manuals (workplace_id, job_name, source_job_key) VALUES (%s, %s, %s) RETURNING id",
            (wp, jobs[job]["job_name"], job)).fetchone()["id"]

        task_ids: dict[str, int] = {}
        approved = 0
        for r in rows:
            tkey = r["task_order"]
            if tkey not in task_ids:
                task_ids[tkey] = conn.execute(
                    "INSERT INTO tasks (manual_id, name, sort_order) VALUES (%s, %s, %s) RETURNING id",
                    (manual_id, r["task_name"], int(tkey))).fetchone()["id"]
            decision = r.get("decision", "").strip()
            ok = decision in ("approve", "edit")
            approved += ok
            final = r["edited_easy_text"].strip() if decision == "edit" and r["edited_easy_text"].strip() \
                else r["easy_text"]
            step_id = conn.execute(
                """
                INSERT INTO steps (task_id, sort_order, action_source, easy_text, easier_text, caution_text, tools,
                  location, evidence_start_ms, evidence_end_ms, photo_path, clip_path, needs_review, review_reason,
                  status, ai_generated, approved_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true, CASE WHEN %s THEN now() END)
                RETURNING id
                """,
                (task_ids[tkey], int(r["order"]), r["action_source"], final, r["easier_text"] or None,
                 r["caution_text"] or None, [t.strip() for t in r["tools"].split(";") if t.strip()],
                 r["location"] or None, _ms(r["evidence_start"]), _ms(r["evidence_end"]),
                 f"{job}/{r['photo']}" if r["photo"] else None, f"{job}/{r['clip']}" if r["clip"] else None,
                 r["needs_review"] == "True", r["review_reason"] or None,
                 "approved" if ok else "in_review", ok),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO step_revisions (step_id, version, source, before, after) VALUES (%s, 1, 'ai', %s, %s)",
                (step_id, Jsonb({"action_source": r["action_source"]}), Jsonb({"easy_text": r["easy_text"]})))
            if decision == "edit":
                conn.execute(
                    "INSERT INTO step_revisions (step_id, version, source, before, after) "
                    "VALUES (%s, 2, 'staff', %s, %s)",
                    (step_id, Jsonb({"easy_text": r["easy_text"]}),
                     Jsonb({"easy_text": final, "note": r.get("reviewer_note", "")})))
        conn.commit()
    result = {"workplace_id": wp, "manual_id": manual_id, "steps": len(rows), "approved": approved}
    print(f"[import] {result}")
    return result


def _delete_manual(conn, manual_id: int) -> None:
    sub = "SELECT s.id FROM steps s JOIN tasks t ON t.id = s.task_id WHERE t.manual_id = %s"
    for table in ("help_events", "step_revisions", "step_checks", "step_refs", "step_embeddings"):
        conn.execute(f"DELETE FROM {table} WHERE step_id IN ({sub})", (manual_id,))
    conn.execute(f"DELETE FROM steps WHERE id IN ({sub})", (manual_id,))
    conn.execute("DELETE FROM tasks WHERE manual_id=%s", (manual_id,))
    conn.execute("DELETE FROM manuals WHERE id=%s", (manual_id,))
