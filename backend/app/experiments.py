"""분석 실험 (data-report.md 의 심화 분석 A·C). 파이프라인 본 단계와 분리해 결과를 data/analysis/<job>/ 에 남긴다.

사용 (backend/ 에서):
    python -m app.experiments extract-runs kitchen_helper --n 5 --variant base     # A: 단계 추출 반복 실행
    python -m app.experiments extract-runs kitchen_helper --n 5 --variant visual   # A: 화면 동작 규칙을 더한 프롬프트
    python -m app.experiments extract-summary kitchen_helper                       # A: 기준 답 대비 집계
    python -m app.experiments easy-metrics kitchen_helper                          # C: 쉬운 안내문 지표

AI 결과와 기준 답의 짝짓기는 app.evaluate.match_steps(문장 유사도)를 쓴다. 애매한 짝은 사람이 pairs 표에서 확인한다.
"""
from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from pathlib import Path

from app.batch import DATA, job_info, load_json, read_csv, save_json, transcript_with_time, video_path, write_csv
from app.config import get_settings
from app.evaluate import _lis_len, match_steps

# A 개선 실험: 1차 평가에서 '화면에만 나온 동작' 이 빠진 것을 보고 더한 규칙
VISUAL_RULE = ("5. 말로 설명하지 않고 화면에만 보이는 동작(문 닫기, 꺼내기, 옮기기, 정리하기 등)도 "
               "빠짐없이 단계로 만든다. 음성 설명이 없으면 근거 구간은 그 동작이 화면에 보이는 구간으로 한다.\n")


def analysis_dir(job: str) -> Path:
    d = DATA / "analysis" / job
    d.mkdir(parents=True, exist_ok=True)
    return d


def gold_rows(job: str) -> list[dict]:
    return sorted(read_csv(DATA / "gold" / f"{job}.csv"), key=lambda r: int(r["order"]))


def flatten(extraction: dict) -> list[dict]:
    out, n = [], 0
    for ti, task in enumerate(extraction["tasks"], start=1):
        for st in sorted(task["steps"], key=lambda x: x["order"]):
            n += 1
            out.append({**st, "order": n, "task_name": task["task_name"], "task_order": ti})
    return out


# --- A. 단계 추출 반복 실행 -----------------------------------------------------------
def extract_runs(job: str, n: int, variant: str) -> None:
    from app.pipeline import gemini
    from app.schemas.llm import EXTRACTION_PROMPT, EXTRACTION_RULES, TaskExtraction

    rules = EXTRACTION_RULES + (VISUAL_RULE if variant == "visual" else "")
    prompt = EXTRACTION_PROMPT.format(job_name=job_info(job)["job_name"], rules=rules,
                                      transcript=transcript_with_time(job))
    f = gemini.upload_file(str(video_path(job)))  # 영상은 한 번만 올리고 여러 번 부른다
    d = analysis_dir(job) / "extract_runs"
    d.mkdir(exist_ok=True)
    start = len(list(d.glob(f"{variant}_*.json")))
    for i in range(start + 1, start + n + 1):
        r = gemini.generate_structured(get_settings().gemini_model_video, [gemini.file_part(f), prompt], TaskExtraction)
        save_json(d / f"{variant}_{i:02d}.json", {"variant": variant, "run": i, **r.model_dump()})
        print(f"[extract-runs] {variant} {i}: 단계 {len(flatten(r.model_dump()))}개")


def extract_summary(job: str) -> None:
    """실행마다 기준 답과 짝짓고, 기준 단계별로 몇 번 빠졌는지 센다."""
    gold = gold_rows(job)
    runs = sorted((analysis_dir(job) / "extract_runs").glob("*.json"))
    run_rows, pair_rows = [], []
    miss = {v: Counter() for v in ("base", "visual")}
    n_runs = Counter()
    for p in runs:
        r = load_json(p)
        v, ai = r["variant"], flatten(r)
        n_runs[v] += 1
        pairs = match_steps([g["action"] for g in gold], [a["action"] for a in ai])
        got = {gi for gi, _, _ in pairs}
        for gi, g in enumerate(gold):
            if gi not in got:
                miss[v][g["order"]] += 1
        ai_used = {ai_i for _, ai_i, _ in pairs}
        run_rows.append({
            "variant": v, "run": r["run"], "ai_steps": len(ai), "matched": len(pairs),
            "missing_rate": round(1 - len(pairs) / len(gold), 3),
            "order_errors": len(pairs) - _lis_len([ai_i for _, ai_i, _ in pairs]),
            "unmatched_ai": len(ai) - len(ai_used),
            "needs_review": sum(1 for a in ai if a.get("needs_review")),
        })
        for gi, ai_i, s in pairs:
            pair_rows.append({"variant": v, "run": r["run"], "gold_order": gold[gi]["order"],
                              "gold_action": gold[gi]["action"], "ai_order": ai[ai_i]["order"],
                              "ai_action": ai[ai_i]["action"], "similarity": round(s, 2), "error_type": ""})
        for ai_i, a in enumerate(ai):
            if ai_i not in ai_used:
                pair_rows.append({"variant": v, "run": r["run"], "gold_order": "", "gold_action": "",
                                  "ai_order": a["order"], "ai_action": a["action"], "similarity": "",
                                  "error_type": ""})
    out = analysis_dir(job)
    write_csv(out / "extract_runs.csv", list(run_rows[0]), run_rows)
    write_csv(out / "extract_pairs.csv", list(pair_rows[0]), pair_rows)

    labels = {r["gold_order"]: r for r in read_csv(out / "gold_evidence_labels.csv")}
    miss_rows = []
    for g in gold:
        lab = labels.get(g["order"], {})
        miss_rows.append({
            "gold_order": g["order"], "action": g["action"],
            "evidence_type": lab.get("evidence_type", ""), "auto_speech": lab.get("auto_speech", ""),
            **{f"miss_{v}": f"{miss[v][g['order']]}/{n_runs[v]}" for v in n_runs},
        })
    write_csv(out / "extract_miss_by_gold.csv", list(miss_rows[0]), miss_rows)
    for v in n_runs:
        rs = [r for r in run_rows if r["variant"] == v]
        avg = sum(r["missing_rate"] for r in rs) / len(rs)
        print(f"[extract-summary] {v}: {len(rs)}회, 단계 수 {sorted(r['ai_steps'] for r in rs)}, 평균 누락 {avg:.1%}")


def evidence_label_template(job: str) -> None:
    """기준 단계마다 근거 유형을 적을 표.
    auto_speech 는 전사문으로 한 자동 추정(참고용), evidence_type 은 사람이 적는다."""
    from kiwipiepy import Kiwi

    from app.pipeline.media import mmss_to_ms as media_ms

    kiwi = Kiwi()
    segs = load_json(DATA / "work" / job / "transcript.json")["segments"]

    def content(text: str) -> set[str]:
        return {t.form for t in kiwi.tokenize(text) if t.tag.split("-")[0] in ("NNG", "NNP", "VV")}

    rows = []
    for g in gold_rows(job):
        a, b = media_ms(g["evidence_start"]), media_ms(g["evidence_end"])
        near = [s for s in segs if s["end_ms"] >= a - 2000 and s["start_ms"] <= b + 2000]
        words = content(g["action"])
        best, best_line = 0.0, ""
        for s in near:
            ov = len(words & content(s["text"])) / (len(words) or 1)
            if ov > best:
                best, best_line = ov, s["text"]
        rows.append({"gold_order": g["order"], "action": g["action"],
                     "evidence_start": g["evidence_start"], "evidence_end": g["evidence_end"],
                     "auto_speech": "있음" if best >= 0.34 else "없음", "auto_speech_line": best_line,
                     "evidence_type": "", "note": ""})
    path = analysis_dir(job) / "gold_evidence_labels.csv"
    if path.exists():  # 사람이 적은 칸은 보존
        prev = {r["gold_order"]: r for r in read_csv(path)}
        for r in rows:
            for c in ("evidence_type", "note"):
                r[c] = prev.get(r["gold_order"], {}).get(c, "")
    write_csv(path, list(rows[0]), rows)
    print(f"[labels] {path}")


# --- C. 쉬운 안내문 지표 ------------------------------------------------------------
SENT = re.compile(r"(?<=[.!?])\s+")


def text_metrics(kiwi, text: str, grade, exempt: set[str] = frozenset()) -> dict:
    sents = [s for s in SENT.split(text.strip()) if s.strip()]
    toks = kiwi.tokenize(text)
    content = [t for t in toks if t.tag.split("-")[0] in ("NNG", "NNP", "VV", "VA", "MAG")]
    verbs_per_sent = []
    for s in sents:
        # 행동 수 근사: 동사(VV) + '하다' 동사(착용하다 = 착용/NNG + 하/XSV). '꽂아 넣다' 같은 이어진 동사는 2로 센다.
        verbs_per_sent.append(sum(1 for t in kiwi.tokenize(s) if t.tag.split("-")[0] in ("VV", "XSV")))
    hard = [t.form for t in content if (g := grade(t.form + ("다" if t.tag.startswith(("VV", "VA")) else "")))
            in ("중급", "고급") or g is None]
    hard_nonterm = [w for w in hard if w not in exempt]
    return {
        "chars": len(text.replace(" ", "")),
        "sentences": len(sents),
        "chars_per_sentence": round(len(text.replace(" ", "")) / max(len(sents), 1), 1),
        "verbs_per_sentence": round(sum(verbs_per_sent) / max(len(sents), 1), 2),
        "content_words": len(content),
        "hard_words": len(hard),
        "hard_ratio": round(len(hard) / max(len(content), 1), 3),
        "hard_list": " ".join(hard),
        # 도구 이름·현장 용어는 바꿀 수 없으므로 뺀 비율 (안내문이 실제로 쉬워졌는지 보는 지표)
        "hard_ratio_nonterm": round(len(hard_nonterm) / max(len(content), 1), 3),
        "hard_nonterm_list": " ".join(hard_nonterm),
    }


def easy_metrics(job: str) -> None:

    cache = load_json(DATA / "work" / "vocab_cache.json")
    # C 는 '사전 등급 그대로' 로 잰다 (사람이 정한 예외를 섞지 않음). 예외 목록의 효과는 vocab_judgement 에서 따로 본다.
    def grade(w: str):
        return cache.get(w, "초급")

    from app.batch import tool_words
    from app.pipeline.easy_text_check import build_kiwi

    terms = {r["term"] for r in read_csv(DATA / "curated/field_terms.csv") if r["job_key"] == job}
    kiwi = build_kiwi(terms)  # 현장 용어가 쪼개지지 않게
    rows = []
    for r in read_csv(DATA / "review" / job / "steps_review.csv"):
        exempt = terms | tool_words([t.strip() for t in r["tools"].split(";") if t.strip()])
        for kind, text in (("source", r["action_source"]), ("easy", r["easy_text"]), ("easier", r["easier_text"])):
            if text:
                rows.append({"order": r["order"], "kind": kind, "text": text,
                             **text_metrics(kiwi, text, grade, exempt)})
    out = analysis_dir(job)
    write_csv(out / "easy_metrics.csv", list(rows[0]), rows)

    summary = []
    for kind in ("source", "easy", "easier"):
        rs = [x for x in rows if x["kind"] == kind]
        summary.append({"kind": kind, "n": len(rs), **{
            k: round(sum(x[k] for x in rs) / len(rs), 2)
            for k in ("chars", "sentences", "chars_per_sentence", "verbs_per_sentence", "hard_ratio",
                      "hard_ratio_nonterm")}})
    write_csv(out / "easy_metrics_summary.csv", list(summary[0]), summary)
    for s in summary:
        print(f"[easy-metrics] {s}")

    # 사전 등급 vs 사람 판단: 사전이 중급 이상/등급 없음으로 본 낱말 중 사람이 '쉬운 말(ignore)' 로 판정한 비율
    over = {r["word"]: r["action"] for r in read_csv(DATA / "curated/vocab_overrides.csv")}
    terms = {r["term"] for r in read_csv(DATA / "curated/field_terms.csv") if r["job_key"] == job}
    judge = []
    for w, g in sorted(cache.items()):
        if g in ("중급", "고급") or g is None:
            human = "현장 용어" if w in terms else {"ignore": "쉬움", "hard": "어려움"}.get(over.get(w, ""), "")
            judge.append({"word": w, "dict_grade": g or "등급 없음", "human": human})
    write_csv(out / "vocab_judgement.csv", ["word", "dict_grade", "human"], judge)
    c = Counter(j["human"] or "미판정" for j in judge)
    print(f"[easy-metrics] 사전 '어려움' {len(judge)}개 중 사람 판단: {dict(c)}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.experiments")
    p.add_argument("cmd", choices=["extract-runs", "extract-summary", "labels", "easy-metrics"])
    p.add_argument("job")
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--variant", choices=["base", "visual"], default="base")
    a = p.parse_args(argv)
    os.chdir(Path(__file__).resolve().parents[1])
    if a.cmd == "extract-runs":
        extract_runs(a.job, a.n, a.variant)
    elif a.cmd == "extract-summary":
        extract_summary(a.job)
    elif a.cmd == "labels":
        evidence_label_template(a.job)
    else:
        easy_metrics(a.job)


if __name__ == "__main__":
    main()
