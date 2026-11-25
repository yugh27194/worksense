"""기준 답(data/gold)과 AI 결과(data/review)를 비교해 인계서 10장 지표를 계산한다.

- 단계 누락 비율: 기준 단계 중 AI 단계와 짝지어지지 않은 비율
- 순서 오류 수: 짝지어진 단계 중 순서가 어긋난 단계 수 (최장 증가 부분열 바깥)
- 주요 정보 보존율: 기준 답의 도구명·수치가 승인된 안내문에 남아 있는 비율

짝짓기는 문장 유사도(difflib) 기준의 단순한 방식이다. 프로토타입 평가용이며, 애매한 짝은 사람이 본다.
"""
from __future__ import annotations

import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

MATCH_THRESHOLD = 0.35
NUM = re.compile(r"\d+(?:\.\d+)?\s*[a-zA-Z가-힣]{0,3}")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.replace(" ", ""), b.replace(" ", "")).ratio()


def _lis_len(seq: list[int]) -> int:
    import bisect

    tails: list[int] = []
    for x in seq:
        i = bisect.bisect_left(tails, x)
        tails[i:i + 1] = [x]
    return len(tails)


def match_steps(gold: list[str], ai: list[str], threshold: float = MATCH_THRESHOLD) -> list[tuple[int, int, float]]:
    """유사도 높은 순으로 1:1 짝짓기. (gold_idx, ai_idx, 유사도) 목록."""
    cands = sorted(((_sim(g, a), gi, ai_i) for gi, g in enumerate(gold) for ai_i, a in enumerate(ai)), reverse=True)
    used_g, used_a, pairs = set(), set(), []
    for s, gi, ai_i in cands:
        if s < threshold:
            break
        if gi in used_g or ai_i in used_a:
            continue
        used_g.add(gi)
        used_a.add(ai_i)
        pairs.append((gi, ai_i, s))
    return sorted(pairs)


def final_text(row: dict[str, str]) -> str:
    return row.get("edited_easy_text") or row.get("easy_text") or ""


def evaluate_job(data_dir: str | Path, job_key: str) -> dict:
    root = Path(data_dir)
    gold = sorted(_rows(root / "gold" / f"{job_key}.csv"), key=lambda r: int(r["order"]))
    review = sorted(_rows(root / "review" / job_key / "steps_review.csv"), key=lambda r: int(r["order"]))
    ai = [r for r in review if r.get("decision", "") != "reject"]

    pairs = match_steps([g["action"] for g in gold], [r["action_source"] for r in ai])
    ai_order = [ai_i for _, ai_i, _ in pairs]
    order_errors = len(pairs) - _lis_len(ai_order)

    key_total = key_kept = 0
    lost: list[str] = []
    for gi, ai_i, _ in pairs:
        text = final_text(ai[ai_i])
        keys = [t.strip() for t in gold[gi]["tools"].split(";") if t.strip()] + NUM.findall(gold[gi]["action"])
        for k in keys:
            key_total += 1
            if k.replace(" ", "") in text.replace(" ", ""):
                key_kept += 1
            else:
                lost.append(f"{gold[gi]['order']}번 단계: {k}")

    matched_gold = {gi for gi, _, _ in pairs}
    return {
        "gold_steps": len(gold),
        "ai_steps": len(ai),
        "matched": len(pairs),
        "missing_rate": round(1 - len(pairs) / len(gold), 3) if gold else None,
        "missing_steps": [g["action"] for i, g in enumerate(gold) if i not in matched_gold],
        "order_errors": order_errors,
        "key_info_retention": round(key_kept / key_total, 3) if key_total else None,
        "key_info_lost": lost,
        "approved": sum(r.get("decision") in ("approve", "edit") for r in review),
    }
