"""인계서 5.6 실행 예 재현. python scripts/easy_text_demo.py [--live]  (--live 는 KRDICT_KEY 필요)"""
import os
import sys

from app.ingest.krdict import lookup_grade
from app.pipeline.easy_text_check import build_kiwi, check

SAMPLE_GRADES = {
    "분리": "중급", "잔여": "고급", "커피": "초급", "찌꺼기": "중급", "제거": "중급",
    "빼다": "초급", "물": "초급", "흘리다": "초급", "남다": "초급", "가루": "초급", "닦다": "초급",
    "우유": "초급", "붓다": "초급", "머신": None,
}

if __name__ == "__main__":
    terms = ["포터필터", "그룹헤드", "스팀피처", "에스프레소"]
    kiwi = build_kiwi(terms)
    if "--live" in sys.argv:
        key = os.environ["KRDICT_KEY"]
        cache: dict = {}

        def grade_fn(w: str) -> str | None:
            if w not in cache:
                cache[w] = lookup_grade(w, key)
            return cache[w]
    else:
        grade_fn = SAMPLE_GRADES.get
    src = "스팀피처에 우유를 200ml 붓고, 포터필터를 분리한 후 잔여 커피 찌꺼기를 제거합니다."
    easy = "스팀피처에 우유를 붓고, 포터필터를 빼서 남은 커피 가루를 3번 닦아요."
    r = check(kiwi, src, easy, tools=["스팀피처", "포터필터"], field_terms=set(terms), grade_fn=grade_fn)
    print("검토할 어휘:", r.hard_words)
    print("누락:", r.missing_info)
    print("임의 추가:", r.added_info)
