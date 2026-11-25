"""5.6 안내문 자동 점검 (규칙 기반).

생성형 AI 에게 다시 묻지 않고 사전 데이터와 규칙으로 점검한다. 인계서 첨부 easy_text_check.py 를 모듈화했다.
1. 현장 용어를 Kiwi 사용자 사전에 등록한다 ('포터필터'가 '포터+필터'로 쪼개지지 않게).
2. 내용어(NNG·NNP·VV·VA·MAG) 기본형을 한국어기초사전 word_grade 와 대조한다. 중급·고급·등급 없음은 '검토할 표현'.
3. 원문과 안내문의 수치·단위, 도구명을 양방향으로 비교해 '누락'과 '임의 추가'를 표시한다.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from kiwipiepy import Kiwi

CONTENT_TAGS = {"NNG", "NNP", "VV", "VA", "MAG"}
HARD_GRADES = {"중급", "고급"}

GradeFn = Callable[[str], str | None]


def build_kiwi(field_terms: list[str] | set[str]) -> Kiwi:
    kiwi = Kiwi()
    for term in field_terms:
        kiwi.add_user_word(term, "NNP", 0)
    return kiwi


def lemmas(kiwi: Kiwi, text: str) -> list[tuple[str, str]]:
    out = []
    for t in kiwi.tokenize(text):
        if t.tag.split("-")[0] in CONTENT_TAGS:
            base = t.form + "다" if t.tag.startswith(("VV", "VA")) else t.form
            out.append((base, t.tag))
    return out


def numbers_with_units(kiwi: Kiwi, text: str) -> list[str]:
    toks = kiwi.tokenize(text)
    out = []
    for i, t in enumerate(toks):
        if t.tag == "SN":
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            unit = nxt.form if nxt is not None and nxt.tag in {"SL", "NNB", "NNG"} else ""
            out.append(t.form + unit)
    return out


@dataclass
class CheckResult:
    hard_words: list[tuple[str, str | None]] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    added_info: list[str] = field(default_factory=list)

    def to_step_checks(self) -> list[tuple[str, dict]]:
        """step_checks(check_type, payload) 행으로 바꾼다."""
        rows: list[tuple[str, dict]] = [("vocab", {"word": w, "grade": g}) for w, g in self.hard_words]
        rows += [("key_info_missing", {"note": n}) for n in self.missing_info]
        rows += [("key_info_added", {"note": n}) for n in self.added_info]
        return rows


def check(kiwi: Kiwi, source: str, easy: str, tools: list[str], field_terms: set[str],
          grade_fn: GradeFn) -> CheckResult:
    res = CheckResult()
    seen: set[str] = set()
    for base, _tag in lemmas(kiwi, easy):
        if base in field_terms or base in seen:
            continue
        seen.add(base)
        g = grade_fn(base)
        if g is None or g in HARD_GRADES:
            res.hard_words.append((base, g))
    src_nums, easy_nums = numbers_with_units(kiwi, source), numbers_with_units(kiwi, easy)
    res.missing_info += [f"수치 누락: {n}" for n in src_nums if n not in easy_nums]
    res.added_info += [f"원문에 없는 수치: {n}" for n in easy_nums if n not in src_nums]
    res.missing_info += [f"도구명 누락: {t}" for t in tools if t not in easy]
    return res


_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"


def _vowel_final(ch: str) -> tuple[str, bool] | None:
    code = ord(ch) - 0xAC00
    if not 0 <= code < 11172:
        return None
    return _JUNG[(code // 28) % 21], code % 28 != 0


def conjugation_errors(kiwi: Kiwi, text: str) -> list[str]:
    """'닦어요' 처럼 받침 있는 어간 뒤 '-아/-어' 모음 어울림이 틀린 곳. 어간이 ㅏ·ㅗ 로 끝나면 '-아', 아니면 '-어'.
    Kiwi 가 어간+어미로 나눈 경우만 본다. '넣아요' 같은 반대 경우는 Kiwi 가 다르게 쪼개서 대부분 못 잡는다.
    불규칙 활용처럼 글자가 바뀐 경우(돕다→도와요)는 보지 않는다."""
    out = []
    toks = kiwi.tokenize(text)
    for a, b in zip(toks, toks[1:], strict=False):
        if a.tag.split("-")[0] not in ("VV", "VA") or not b.tag.startswith("E"):
            continue
        stem_end = a.start + a.len
        if text[a.start:stem_end] != a.form or b.start != stem_end or stem_end >= len(text):
            continue
        vf = _vowel_final(a.form[-1])
        first = text[stem_end]
        if not vf or not vf[1] or first not in "아어":
            continue
        want = "아" if vf[0] in ("ㅏ", "ㅗ") else "어"
        if first != want:
            word = text[a.start:stem_end + b.len]
            out.append(f"'{word}' → '{a.form}{want}{word[len(a.form) + 1:]}'")
    return out
