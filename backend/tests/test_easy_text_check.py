"""인계서 5.6 / 부록 C.2·C.4 재현."""
import pytest

from app.pipeline.easy_text_check import build_kiwi, check, lemmas

TERMS = ["포터필터", "그룹헤드", "스팀피처", "에스프레소"]
GRADES = dict.fromkeys(["우유", "붓다", "빼다", "남다", "커피", "가루", "닦다"], "초급")


@pytest.fixture(scope="module")
def kiwi():
    return build_kiwi(TERMS)


def test_field_term_not_split(kiwi):
    forms = [w for w, _ in lemmas(kiwi, "포터필터를 머신에서 빼요.")]
    assert "포터필터" in forms
    assert "필터" not in forms


def test_missing_and_added_numbers(kiwi):
    src = "스팀피처에 우유를 200ml 붓고, 포터필터를 분리한 후 잔여 커피 찌꺼기를 제거합니다."
    easy = "스팀피처에 우유를 붓고, 포터필터를 빼서 남은 커피 가루를 3번 닦아요."
    r = check(kiwi, src, easy, tools=["스팀피처", "포터필터"], field_terms=set(TERMS), grade_fn=GRADES.get)
    assert r.missing_info == ["수치 누락: 200ml"]
    assert r.added_info == ["원문에 없는 수치: 3번"]
    assert r.hard_words == []


def test_hard_and_ungraded_words_flagged(kiwi):
    r = check(kiwi, "잔여 커피를 제거합니다.", "잔여 커피를 제거해요.", tools=[], field_terms=set(),
              grade_fn={"잔여": "고급", "커피": "초급"}.get)
    words = dict(r.hard_words)
    assert words["잔여"] == "고급"
    assert "커피" not in words
    assert "제거" in words and words["제거"] is None  # 등급 없음도 검토 대상


def test_missing_tool(kiwi):
    r = check(kiwi, "", "우유를 부어요.", tools=["스팀피처"], field_terms=set(TERMS), grade_fn=GRADES.get)
    assert "도구명 누락: 스팀피처" in r.missing_info
    assert ("key_info_missing", {"note": "도구명 누락: 스팀피처"}) in r.to_step_checks()


def test_conjugation_errors():
    from kiwipiepy import Kiwi

    from app.pipeline.easy_text_check import conjugation_errors

    k = Kiwi()
    assert conjugation_errors(k, "행주로 식탁을 닦어요.") == ["'닦어요' → '닦아요'"]
    assert conjugation_errors(k, "그릇을 쌓어요.") == ["'쌓어요' → '쌓아요'"]
    for ok in ("식탁을 닦아요.", "세제를 넣어요.", "다듬어요", "도와요", "들어요", "켜요", "해요"):
        assert conjugation_errors(k, ok) == [], ok
