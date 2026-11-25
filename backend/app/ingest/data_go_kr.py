"""4.2~4.5 공공데이터포털 수집기 (NCS·장애인 고용직무분류·복지서비스).

- 인증키(serviceKey)는 URL 쿼리로 가므로 요청 URL 을 로그에 남기지 않는다 (9.3).
- 명세는 Swagger 로만 확인했다. 첫 호출 때 응답 구조를 다시 확인하고 아래 TODO 를 고친다 (12장 #7, #8).
- 수집 결과는 ingest_runs 에 기록한다. 실패해도 저장본으로 서비스를 이어간다 (9.2).
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator

import httpx

log = logging.getLogger(__name__)

NCS_BASE = "https://apis.data.go.kr/B490007/ncsInfo"
JOBCODE_BASE = "https://apis.data.go.kr/B552583/jobcode"
WELFARE_CENTRAL_BASE = "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001"
WELFARE_LOCAL_BASE = "https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations"

# 공공데이터포털 공통 오류 코드
ERROR_CODES = {"999": "인증 실패", "002": "데이터 없음", "009": "필수 파라미터 누락"}


class DataGoKrClient:
    def __init__(self, service_key: str, timeout: float = 30):
        self._key = service_key
        # event_hooks 로 URL 을 찍지 않는다. httpx 기본 로그도 WARNING 으로 올린다.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self._http = httpx.Client(timeout=timeout)

    def get_xml(self, url: str, retries: int = 4, **params) -> ET.Element:
        for attempt in range(retries):
            try:
                r = self._http.get(url, params={"serviceKey": self._key, **params})
                r.raise_for_status()
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                # 예외 메시지에 URL(키 포함)이 들어가므로 종류만 남긴다 (9.3)
                if attempt == retries - 1:
                    raise RuntimeError(f"data.go.kr 요청 실패: {type(e).__name__}") from None
                time.sleep(2 * (attempt + 1))
        root = ET.fromstring(r.content)
        # 응답 형식이 API 마다 다르다: 표준(header/resultCode, item, totalCount) / NCS(dataInfo/code, row, totCnt)
        code = root.findtext(".//resultCode") or root.findtext("./dataInfo/code")
        if code and code.strip("0"):
            msg = root.findtext(".//resultMsg") or root.findtext("./dataInfo/message")
            raise RuntimeError(f"data.go.kr 오류 {code}: {ERROR_CODES.get(code, msg)}")
        return root

    def paged_items(self, url: str, rows: int = 500, **params) -> Iterator[dict[str, str]]:
        page = 1
        while True:
            root = self.get_xml(url, pageNo=page, numOfRows=rows, **params)
            items = [{c.tag: (c.text or "") for c in it} for it in [*root.iter("item"), *root.iter("row")]]
            yield from items
            total = int(root.findtext(".//totalCount") or root.findtext(".//totCnt") or 0)
            if not items or page * rows >= total:
                break
            page += 1


# --- 4.2 NCS ---------------------------------------------------------------
def fetch_ncs_classification(client: DataGoKrClient) -> Iterator[dict[str, str]]:
    """/ncsCdInfo 전체. 키워드 검색이 없으므로 전체를 저장해 두고 세분류명으로 찾는다."""
    return client.paged_items(f"{NCS_BASE}/ncsCdInfo", returnType="xml")


def fetch_ncs_comp_units(client: DataGoKrClient, duty_cd: str) -> Iterator[dict[str, str]]:
    return client.paged_items(f"{NCS_BASE}/ncsCompeUnitInfo", dutyCd=duty_cd, returnType="xml")


def fetch_ncs_ksa(client: DataGoKrClient, duty_cd: str, comp_unit_cd: str | None = None):
    # TODO(12장 #7): gbnName 에 어떤 값(수행준거·지식·기술·태도)이 오는지 첫 호출로 확인
    params = {"dutyCd": duty_cd, "returnType": "xml"}
    if comp_unit_cd:
        params["compUnitCd"] = comp_unit_cd
    return client.paged_items(f"{NCS_BASE}/ncsKsaInfo", **params)


# --- 4.3 장애인 고용직무분류 --------------------------------------------------
def fetch_jobcodes(client: DataGoKrClient) -> Iterator[dict[str, str]]:
    # TODO(12장 #8): Swagger 의 jobCdNm/jobCdLevel 설명이 뒤바뀌어 있음. 실제 응답으로 확인
    return client.paged_items(f"{JOBCODE_BASE}/job_code")


# --- 4.4·4.5 복지서비스 (P1, MVP 포함 여부 미결 12장 #6) ---------------------------
def fetch_welfare_central(client: DataGoKrClient, intrs_thema: str | None = None):
    """개발계정 하루 100건 → 관심주제(일자리 등)로 좁혀 수집."""
    params = {"callTp": "L", "srchKeyCode": "003"}
    if intrs_thema:
        params["intrsThemaArray"] = intrs_thema
    return client.paged_items(f"{WELFARE_CENTRAL_BASE}/NationalWelfarelistV001", **params)


def fetch_welfare_local(client: DataGoKrClient, ctpv_nm: str | None = None, sgg_nm: str | None = None):
    params = {k: v for k, v in {"ctpvNm": ctpv_nm, "sggNm": sgg_nm}.items() if v}
    return client.paged_items(f"{WELFARE_LOCAL_BASE}/LcgvWelfarelist", **params)
