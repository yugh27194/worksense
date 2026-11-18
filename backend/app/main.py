"""일머RE API 서버. 실행: uvicorn app.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
