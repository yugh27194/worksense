"""내부 API: 공공데이터 수집 (스케줄러가 호출). NCS·직무분류 주 1회, 복지서비스 하루 1회 (9.2)."""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/internal", tags=["internal"])

SOURCES = {"ncs", "jobcode", "welfare_central", "welfare_local"}


@router.post("/ingest/{source}")
def ingest(source: str):
    if source not in SOURCES:
        raise HTTPException(404)
    # TODO: app.ingest.data_go_kr 로 수집 → upsert → ingest_runs 기록. 내부망/토큰으로 보호.
    raise HTTPException(501, "TODO")
