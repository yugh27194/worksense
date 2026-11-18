"""4.6 한국어기초사전 오픈 API (국립국어원). 하루 50,000건 → vocab_cache 로 중복 조회를 막는다."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

KRDICT_URL = "https://krdict.korean.go.kr/api/search"


def parse_grade(xml_bytes: bytes, word: str) -> str | None:
    """응답 XML 에서 표제어가 일치하는 첫 item 의 word_grade. 선택 필드라 없으면 None."""
    root = ET.fromstring(xml_bytes)
    for item in root.iter("item"):
        if item.findtext("word") == word:
            return item.findtext("word_grade") or None
    return None


def lookup_grade(word: str, key: str, client: httpx.Client | None = None) -> str | None:
    c = client or httpx.Client(timeout=10)
    r = c.get(KRDICT_URL, params={"key": key, "q": word})
    r.raise_for_status()
    return parse_grade(r.content, word)


def cached_grade_fn(conn, key: str):
    """vocab_cache 를 먼저 보고, 없으면 API 를 조회해 저장하는 grade_fn."""
    client = httpx.Client(timeout=10)

    def grade(word: str) -> str | None:
        row = conn.execute("SELECT word_grade FROM vocab_cache WHERE lemma = %s", (word,)).fetchone()
        if row is not None:
            return row["word_grade"]
        g = lookup_grade(word, key, client)
        conn.execute(
            "INSERT INTO vocab_cache (lemma, word_grade, fetched_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (lemma) DO NOTHING", (word, g))
        return g

    return grade
