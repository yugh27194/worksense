"""공공 직업정보 영상 → 직무별 기본 매뉴얼 일괄 생성 (인계서 5.1~5.7, docs/workflow.md).

사용 (backend/ 에서):
    python -m app.batch all kitchen_helper            # 전처리부터 검토표까지
    python -m app.batch transcribe kitchen_helper     # 한 단계만 다시
    python -m app.batch import kitchen_helper         # 검수 끝난 검토표를 DB 에 반영

단계마다 결과를 파일로 남기므로 어느 단계부터든 다시 돌릴 수 있다.
- data/work/<job>/      중간 산출물 (git 제외): audio.wav, part_*.wav, transcript.json, steps.json, gaps.json,
                        easy.json, checks.json, media/*.jpg|mp4
- data/review/<job>/    사람이 보는 파일 (git 포함): transcript.csv, steps_review.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from app.config import get_settings
from app.pipeline import media

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

REVIEW_COLUMNS = [
    "order", "task_name", "task_order", "action_source", "tools", "location", "cautions",
    "easy_text", "easier_text", "caution_text", "source_numbers",
    "evidence_start", "evidence_end", "needs_review", "review_reason", "checks", "gaps",
    "photo", "clip",
    "decision", "edited_easy_text", "reviewer_note",
]
REVIEWER_COLUMNS = ("decision", "edited_easy_text", "reviewer_note")


# --- 경로·입출력 ---------------------------------------------------------------
def work_dir(job: str) -> Path:
    d = DATA / "work" / job
    d.mkdir(parents=True, exist_ok=True)
    return d


def review_dir(job: str) -> Path:
    d = DATA / "review" / job
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def job_info(job: str) -> dict[str, str]:
    for row in read_csv(DATA / "curated/jobs.csv"):
        if row["job_key"] == job:
            return row
    raise SystemExit(f"data/curated/jobs.csv 에 job_key '{job}' 가 없습니다 (notebooks/02 참고)")


def video_path(job: str) -> Path:
    info = job_info(job)
    p = DATA / "raw/media" / (info.get("video_file") or f"{job}.mp4")
    if not p.exists():
        raise SystemExit(f"영상이 없습니다: {p}")
    return p


def ms_to_mmss(ms: int) -> str:
    return media.ms_to_mmss(ms)


# --- 5.1 전처리 ----------------------------------------------------------------
def stage_preprocess(job: str) -> None:
    wd = work_dir(job)
    wav = media.extract_audio(video_path(job), wd)
    for old in wd.glob("part_*.wav"):
        old.unlink()
    parts = media.split_audio(wav, wd)
    save_json(wd / "parts.json", [{"file": p.name, "offset_ms": off} for p, off in parts])
    print(f"[preprocess] 오디오 조각 {len(parts)}개")


# --- 5.2 전사 ------------------------------------------------------------------
def stage_transcribe(job: str) -> None:
    from app.pipeline import gemini
    from app.schemas.llm import TRANSCRIBE_PROMPT, Transcript

    s = get_settings()
    wd = work_dir(job)
    segments = []
    for part in load_json(wd / "parts.json"):
        t = gemini.generate_structured(s.gemini_model_transcribe,
                                       [gemini.audio_part(str(wd / part["file"])), TRANSCRIBE_PROMPT], Transcript)
        for seg in t.segments:  # 조각 기준 시각 + 조각 시작 오프셋 = 원본 영상 시각 (5.1)
            segments.append({
                "start_ms": media.mmss_to_ms(seg.start) + part["offset_ms"],
                "end_ms": media.mmss_to_ms(seg.end) + part["offset_ms"],
                "text": seg.text.strip(),
            })
    save_json(wd / "transcript.json", {"model": s.gemini_model_transcribe, "segments": segments})
    write_csv(review_dir(job) / "transcript.csv", ["start", "end", "text"],
              [{"start": ms_to_mmss(x["start_ms"]), "end": ms_to_mmss(x["end_ms"]), "text": x["text"]}
               for x in segments])
    print(f"[transcribe] 문장 {len(segments)}개")


def transcript_with_time(job: str) -> str:
    """5.3 프롬프트용 '[MM:SS] 문장' 형식."""
    segs = load_json(work_dir(job) / "transcript.json")["segments"]
    return "\n".join(f"[{ms_to_mmss(x['start_ms'])}] {x['text']}" for x in segs)


# --- 5.3 단계 추출 ---------------------------------------------------------------
def stage_extract(job: str) -> None:
    from app.pipeline import gemini
    from app.schemas.llm import EXTRACTION_PROMPT, EXTRACTION_RULES, TaskExtraction

    s = get_settings()
    wd = work_dir(job)
    info = job_info(job)
    f = gemini.upload_file(str(video_path(job)))
    prompt = EXTRACTION_PROMPT.format(job_name=info["job_name"], rules=EXTRACTION_RULES,
                                      transcript=transcript_with_time(job))
    result = gemini.generate_structured(s.gemini_model_video, [gemini.file_part(f), prompt], TaskExtraction)
    save_json(wd / "steps.json", result.model_dump())
    n = sum(len(t.steps) for t in result.tasks)
    print(f"[extract] 업무 {len(result.tasks)}개, 단계 {n}개")


def flat_steps(job: str) -> list[dict]:
    """업무별 단계를 전체 순번(order)으로 펼친다. 검토표·평가·안내문 단계가 같은 order 를 쓴다."""
    out, n = [], 0
    for ti, task in enumerate(load_json(work_dir(job) / "steps.json")["tasks"], start=1):
        for st in sorted(task["steps"], key=lambda x: x["order"]):
            n += 1
            out.append({**st, "order": n, "task_name": task["task_name"], "task_order": ti})
    return out


def steps_text(steps: list[dict]) -> str:
    return "\n".join(
        f"{s['order']}. {s['action']} | 도구: {', '.join(s['tools']) or '-'} | 위치: {s.get('location') or '-'}"
        f" | 주의: {'; '.join(s['cautions']) or '-'}" for s in steps)


# --- 5.4 공공 직무데이터 누락 점검 ---------------------------------------------------
def public_reference(job: str) -> tuple[str, str]:
    info = job_info(job)
    jobcode_txt = ncs_txt = ""
    if info.get("job_cd"):
        for r in read_csv(DATA / "raw/api/jobcode.csv"):
            if r.get("jobCd") == info["job_cd"]:
                jobcode_txt = r.get("jobTask", "")
    if info.get("ncs_duty_cd"):
        rows = read_csv(DATA / f"raw/api/ncs_ksa_{info['ncs_duty_cd']}.csv")
        ncs_txt = "\n".join(f"- [{r.get('compUnitName', '')}] {r.get('gbnVal', '')}" for r in rows
                            if r.get("gbnVal"))
    return jobcode_txt, ncs_txt


def stage_match(job: str) -> None:
    from app.pipeline import gemini
    from app.schemas.llm import GAP_PROMPT, GapReport

    wd = work_dir(job)
    jobcode_txt, ncs_txt = public_reference(job)
    if not (jobcode_txt or ncs_txt):
        save_json(wd / "gaps.json", {"gaps": [], "skipped": "jobs.csv 에 확정 코드 또는 data/raw/api 원천 파일 없음"})
        print("[match] 건너뜀: 확정된 직무 코드/공공데이터 원문이 아직 없음 (notebooks/01·02 후 다시 실행)")
        return
    prompt = GAP_PROMPT.format(job_name=job_info(job)["job_name"], steps=steps_text(flat_steps(job)),
                               jobcode=jobcode_txt or "(없음)", ncs=ncs_txt or "(없음)")
    rep = gemini.generate_structured(get_settings().gemini_model_video, [prompt], GapReport)
    save_json(wd / "gaps.json", rep.model_dump())
    print(f"[match] 누락 후보 {len(rep.gaps)}건")


# --- 5.5 쉬운 안내문 -------------------------------------------------------------
def stage_easy(job: str) -> None:
    from app.pipeline import gemini
    from app.schemas.llm import EASY_PROMPT, EasyTextBatch

    steps = flat_steps(job)
    rep = gemini.generate_structured(get_settings().gemini_model_text, [EASY_PROMPT.format(steps=steps_text(steps))],
                                     EasyTextBatch)
    got = {i.order for i in rep.items}
    missing = [s["order"] for s in steps if s["order"] not in got]
    save_json(work_dir(job) / "easy.json", rep.model_dump())
    print(f"[easy] 안내문 {len(rep.items)}개" + (f", 빠진 단계 {missing}" if missing else ""))


# --- 5.6 자동 점검 ---------------------------------------------------------------
def make_grade_fn(job: str):
    """어휘 등급: vocab_overrides → 캐시 → 한국어기초사전 API. 키가 없으면 등급 점검을 건너뛴다."""
    overrides = {r["word"]: r["action"] for r in read_csv(DATA / "curated/vocab_overrides.csv")}
    cache_path = DATA / "work" / "vocab_cache.json"
    cache: dict[str, str | None] = load_json(cache_path) if cache_path.exists() else {}
    key = get_settings().krdict_key
    if not key:
        print("[check] KRDICT_KEY 없음 → 어휘 등급 점검 건너뜀 (수치·도구명 대조는 실행)")

    def grade(word: str) -> str | None:
        if overrides.get(word) == "ignore":
            return "초급"
        if overrides.get(word) == "hard":
            return "고급"
        if not key:
            return "초급"
        if word not in cache:
            from app.ingest.krdict import lookup_grade

            cache[word] = lookup_grade(word, key)
            save_json(cache_path, cache)
        return cache[word]

    return grade


def stage_check(job: str) -> None:
    from app.pipeline.easy_text_check import build_kiwi, check

    terms = {r["term"] for r in read_csv(DATA / "curated/field_terms.csv") if r["job_key"] == job}
    kiwi = build_kiwi(terms)
    grade = make_grade_fn(job)
    easy = {i["order"]: i for i in load_json(work_dir(job) / "easy.json")["items"]}
    out = {}
    for st in flat_steps(job):
        e = easy.get(st["order"])
        if not e:
            continue
        source = " ".join([st["action"], *st["cautions"]])
        target = " ".join(x for x in [e["easy_text"], e.get("caution_text") or ""] if x)
        r = check(kiwi, source, target, tools=st["tools"], field_terms=terms, grade_fn=grade)
        rows = [{"type": t, **p} for t, p in r.to_step_checks()]
        if e.get("easier_text"):  # 「더 쉽게」 문장도 수치·도구명 누락을 본다 (어휘는 easy_text 와 겹치므로 생략)
            easier = " ".join(x for x in [e["easier_text"], e.get("caution_text") or ""] if x)
            r2 = check(kiwi, source, easier, tools=st["tools"], field_terms=terms, grade_fn=grade)
            rows += [{"type": t, "note": f"더 쉽게 문장 {p['note']}"} for t, p in r2.to_step_checks()
                     if t != "vocab"]
        out[st["order"]] = rows
    save_json(work_dir(job) / "checks.json", out)
    print(f"[check] 경고 있는 단계 {sum(1 for v in out.values() if v)}개")


# --- 5.7 사진·클립 ---------------------------------------------------------------
def stage_assets(job: str) -> None:
    import subprocess

    video = video_path(job)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(video)], capture_output=True, text=True, check=True).stdout.strip())
    md = work_dir(job) / "media"
    md.mkdir(exist_ok=True)
    n = 0
    for st in flat_steps(job):
        try:
            a = media.mmss_to_ms(st["evidence_start"]) / 1000
            b = media.mmss_to_ms(st["evidence_end"]) / 1000
        except ValueError:
            continue
        if b <= a:
            b = a + 1
        media.extract_frame(video, min((a + b) / 2, dur - 0.1), md / f"step{st['order']:03d}.jpg")
        s, e = media.clip_window(a, b, dur)
        media.extract_clip(video, s, e, md / f"step{st['order']:03d}.mp4")
        n += 1
    print(f"[assets] 사진·클립 {n}쌍")


# --- 검토표 내보내기 -------------------------------------------------------------
def stage_export(job: str) -> None:
    wd = work_dir(job)
    easy = {i["order"]: i for i in load_json(wd / "easy.json")["items"]} if (wd / "easy.json").exists() else {}
    checks = load_json(wd / "checks.json") if (wd / "checks.json").exists() else {}
    gaps = load_json(wd / "gaps.json").get("gaps", []) if (wd / "gaps.json").exists() else []
    path = review_dir(job) / "steps_review.csv"
    prev = {r["order"]: r for r in read_csv(path)}  # 이미 적어 둔 검수 열은 보존
    rows = []
    for st in flat_steps(job):
        o = st["order"]
        e = easy.get(o, {})
        mfile = wd / "media" / f"step{o:03d}"
        row = {
            "order": o, "task_name": st["task_name"], "task_order": st["task_order"],
            "action_source": st["action"], "tools": "; ".join(st["tools"]), "location": st.get("location") or "",
            "cautions": "; ".join(st["cautions"]),
            "easy_text": e.get("easy_text", ""), "easier_text": e.get("easier_text", ""),
            "caution_text": e.get("caution_text") or "", "source_numbers": "; ".join(e.get("source_numbers", [])),
            "evidence_start": st["evidence_start"], "evidence_end": st["evidence_end"],
            "needs_review": st["needs_review"], "review_reason": st.get("review_reason") or "",
            "checks": " / ".join(_check_label(c) for c in checks.get(str(o), checks.get(o, []))),
            "gaps": " / ".join(f"[{g['source']} {g['gap_type']}] {g['criterion']}" for g in gaps
                               if g.get("related_step_order") == o),
            "photo": f"{mfile.name}.jpg" if mfile.with_suffix(".jpg").exists() else "",
            "clip": f"{mfile.name}.mp4" if mfile.with_suffix(".mp4").exists() else "",
        }
        for c in REVIEWER_COLUMNS:
            row[c] = prev.get(str(o), {}).get(c, "")
        rows.append(row)
    write_csv(path, REVIEW_COLUMNS, rows)
    unlinked = [g for g in gaps if not g.get("related_step_order")]
    if unlinked:
        write_csv(review_dir(job) / "gaps_unlinked.csv", ["source", "gap_type", "criterion", "note"], unlinked)
    print(f"[export] {path} ({len(rows)}행), 단계에 안 붙은 누락 후보 {len(unlinked)}건")


def _check_label(c: dict) -> str:
    if c["type"] == "vocab":
        return f"어려운 낱말: {c['word']}({c.get('grade') or '등급 없음'})"
    return c.get("note", c["type"])


STAGES = {
    "preprocess": stage_preprocess,
    "transcribe": stage_transcribe,
    "extract": stage_extract,
    "match": stage_match,
    "easy": stage_easy,
    "check": stage_check,
    "assets": stage_assets,
    "export": stage_export,
}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.batch")
    p.add_argument("stage", choices=[*STAGES, "all", "import"])
    p.add_argument("job")
    p.add_argument("--from", dest="start", choices=list(STAGES), help="all 과 함께: 이 단계부터")
    a = p.parse_args(argv)
    os.chdir(ROOT / "backend")
    if a.stage == "import":
        from app.importer import import_job

        import_job(a.job)
    elif a.stage == "all":
        names = list(STAGES)
        for name in names[names.index(a.start) if a.start else 0:]:
            STAGES[name](a.job)
    else:
        STAGES[a.stage](a.job)


if __name__ == "__main__":
    main()
