"""5.10 질의응답과 단계적 도움, 5.11 반복 질문 묶기.

'근거 없는 답변 0건' 안전장치: 검색 유사도가 임계값보다 낮거나, 모델 답변의 step_ids 가 비었거나
검색 결과에 없는 단계를 가리키면 답변을 버리고 담당자 연결로 바꾼다.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.llm import Answer

# 단계적 도움 (확정): 0 간결한 문장 → 1 위치 표시 사진 → 2 작업 영상 → 3 더 작은 단위 설명 → 4 담당자 연결
HELP_LEVELS = ("text", "photo", "clip", "substeps", "handoff")
HANDOFF_LEVEL = len(HELP_LEVELS) - 1


@dataclass
class Retrieved:
    step_id: int
    similarity: float  # 1 - cosine distance


def has_evidence(hits: list[Retrieved], min_similarity: float) -> bool:
    return bool(hits) and max(h.similarity for h in hits) >= min_similarity


def validate_answer(answer: Answer, hits: list[Retrieved]) -> Answer:
    """검색된 단계만 근거로 인정한다. 위반하면 담당자 연결로 바꾼다."""
    allowed = {h.step_id for h in hits}
    if answer.needs_handoff or not answer.step_ids or not set(answer.step_ids) <= allowed:
        return Answer(answer_text="담당자에게 물어볼게요. 잠시만 기다려 주세요.", step_ids=[], needs_handoff=True)
    return answer


def next_help_level(current: int) -> int:
    return min(current + 1, HANDOFF_LEVEL)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def group_repeated(vectors: dict[int, list[float]], threshold: float) -> list[list[int]]:
    """질문 벡터를 코사인 유사도 threshold 이상끼리 묶는다(단일 연결). MVP 규모에서는 O(n²)로 충분."""
    ids = list(vectors)
    parent = {i: i for i in ids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if cosine(vectors[a], vectors[b]) >= threshold:
                parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]
