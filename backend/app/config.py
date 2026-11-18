"""환경 설정. 키는 환경변수(.env)로만 받고 코드·로그에 남기지 않는다 (인계서 9.3)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql://worksense:worksense@localhost:5432/worksense"
    storage_dir: Path = Path("./storage")

    gemini_api_key: str = ""
    gemini_model_video: str = "gemini-3.8-flash"
    gemini_model_transcribe: str = "gemini-3.5-transcribe"
    gemini_model_text: str = "gemini-3.5-flash-lite"
    gemini_model_embed: str = "gemini-embedding-2"
    embed_dim: int = 1536  # pgvector HNSW 인덱스 한도(2,000) 때문에 1,536차원 (인계서 3.4)

    data_go_kr_key: str = ""
    krdict_key: str = ""

    rag_top_k: int = 3
    rag_min_similarity: float = 0.6  # 시연 데이터로 보정 (12장 #10)
    repeat_question_similarity: float = 0.85

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
