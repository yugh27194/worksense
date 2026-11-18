"""PostgreSQL 연결 풀. ORM 없이 migrations/*.sql 과 같은 SQL 을 그대로 쓴다."""
from collections.abc import Iterator
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(get_settings().database_url, kwargs={"row_factory": dict_row}, open=True)
    return _pool


@contextmanager
def connect() -> Iterator:
    with get_pool().connection() as conn:
        yield conn


def get_conn() -> Iterator:
    """FastAPI 의존성."""
    with connect() as conn:
        yield conn
