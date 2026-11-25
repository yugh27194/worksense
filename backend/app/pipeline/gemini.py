"""Gemini 호출부. SDK 파라미터 이름(구조화 출력·임베딩 차원 지정 방식)은 버전마다 다르므로 여기에만 둔다.

모델 역할 (인계서 3.3·9.5):
- gemini-3.8-flash       : 영상 분석·단계 추출·매칭 (무거운 작업)
- gemini-3.5-transcribe  : 음성 전사 (오디오만, ko-KR, 단어 타임스탬프 ↔ 사용자 어휘 동시 사용 불가)
- gemini-3.5-flash-lite  : 안내문 재작성·답변 생성 (고빈도 작업)
- gemini-embedding-2     : 1,536차원 임베딩

구현 시점의 공식 문서를 기준으로 맞춘다. 실제 영상은 유료 키 환경에서만 처리한다 (9.1).
"""
from __future__ import annotations

from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)


@lru_cache
def client():
    from google import genai

    key = get_settings().gemini_api_key
    if not key:
        raise RuntimeError("GEMINI_API_KEY 가 없습니다 (.env 확인)")
    return genai.Client(api_key=key)


def generate_structured(model: str, contents: list, schema: type[T], system: str | None = None) -> T:
    """구조화 출력 호출 후 Pydantic 으로 검증해 돌려준다."""
    from google.genai import types

    resp = client().models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return schema.model_validate_json(resp.text)


def embed(texts: list[str]) -> list[list[float]]:
    from google.genai import types

    s = get_settings()
    resp = client().models.embed_content(
        model=s.gemini_model_embed,
        contents=texts,
        config=types.EmbedContentConfig(output_dimensionality=s.embed_dim),
    )
    # TODO(12장 #10): 차원 축소 시 정규화 필요 여부를 공식 문서로 확인. 우선 L2 정규화한다.
    out = []
    for e in resp.embeddings:
        v = list(e.values)
        n = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / n for x in v])
    return out


def upload_file(path: str, timeout_s: int = 900):
    """100MB 초과·10분 초과·재사용 파일은 File API 업로드 권장 (3.4). 처리가 끝나(ACTIVE) 쓸 수 있을 때까지 기다린다."""
    import time

    from google.genai import types

    f = client().files.upload(file=path)
    deadline = time.monotonic() + timeout_s
    while f.state == types.FileState.PROCESSING:
        if time.monotonic() > deadline:
            raise TimeoutError(f"File API 처리 대기 시간 초과: {path}")
        time.sleep(5)
        f = client().files.get(name=f.name)
    if f.state != types.FileState.ACTIVE:
        raise RuntimeError(f"File API 처리 실패: {f.state}")
    return f


def audio_part(path: str):
    from google.genai import types

    with open(path, "rb") as fh:
        return types.Part.from_bytes(data=fh.read(), mime_type="audio/wav")


def file_part(f):
    from google.genai import types

    return types.Part.from_uri(file_uri=f.uri, mime_type=f.mime_type)
