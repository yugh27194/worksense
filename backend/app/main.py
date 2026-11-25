"""일머RE API 서버. 실행: uvicorn app.main:app --reload"""
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import internal, staff, worker
from app.config import get_settings

app = FastAPI(title="일머RE API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(staff.router)
app.include_router(worker.router)
app.include_router(internal.router)


@app.get("/health")
def health():
    return {"status": "ok"}


MEDIA_NAME = re.compile(r"^[a-z0-9_]+/step\d{3}\.(jpg|mp4)$")


@app.get("/files/{job}/{name}")
def media_file(job: str, name: str):
    """단계 사진·클립. 프로토타입에서는 경로 검사만 한다 (운영 시 서명된 URL, 인계서 9.3)."""
    rel = f"{job}/{name}"
    if not MEDIA_NAME.match(rel):
        raise HTTPException(404)
    from app import batch

    path = batch.DATA / "work" / job / "media" / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)
