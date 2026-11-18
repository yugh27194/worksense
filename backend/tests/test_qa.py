from app.pipeline.qa import (
    HANDOFF_LEVEL,
    Retrieved,
    group_repeated,
    has_evidence,
    next_help_level,
    validate_answer,
)
from app.schemas.llm import Answer

HITS = [Retrieved(1, 0.82), Retrieved(2, 0.71)]


def test_evidence_threshold():
    assert has_evidence(HITS, 0.6)
    assert not has_evidence(HITS, 0.9)
    assert not has_evidence([], 0.1)


def test_answer_must_cite_retrieved_steps():
    ok = Answer(answer_text="우유를 부어요.", step_ids=[1], needs_handoff=False)
    assert validate_answer(ok, HITS) == ok
    for bad in (Answer(answer_text="x", step_ids=[], needs_handoff=False),
                Answer(answer_text="x", step_ids=[99], needs_handoff=False)):
        assert validate_answer(bad, HITS).needs_handoff


def test_help_levels_cap_at_handoff():
    assert next_help_level(0) == 1
    assert next_help_level(HANDOFF_LEVEL) == HANDOFF_LEVEL


def test_group_repeated():
    v = {1: [1.0, 0.0], 2: [0.99, 0.05], 3: [0.0, 1.0]}
    assert group_repeated(v, 0.85) == [[1, 2]]
