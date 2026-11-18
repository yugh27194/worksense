"""Gemini 구조화 출력 스키마와 함수 호출 정의 (인계서 5.3·5.4·5.5·5.10).

Pydantic 모델을 구조화 출력의 response_schema 로 넘기고, 응답도 같은 모델로 검증한다.
Gemini SDK 파라미터 이름은 버전마다 다르므로 호출부(app/pipeline/gemini.py)에 모아 둔다.
"""
from typing import Literal

from pydantic import BaseModel, Field


# 5.3 작업 단계 추출 ----------------------------------------------------------
class ExtractedStep(BaseModel):
    order: int
    action: str = Field(description="원본 기준 행동 하나")
    tools: list[str]
    location: str | None
    cautions: list[str]
    evidence_start: str = Field(description="MM:SS")
    evidence_end: str = Field(description="MM:SS")
    transcript_quote: str | None = None
    needs_review: bool
    review_reason: str | None = None


class StepExtraction(BaseModel):
    task_name: str = Field(description="업무명. 예: 오픈 준비")
    steps: list[ExtractedStep]


EXTRACTION_RULES = """\
1. 화면과 전사문에서 직접 확인되는 내용만 쓴다.
2. 한 단계에는 행동 하나만 담는다.
3. 기기 조작법, 수치, 사업장마다 다른 절차처럼 확정할 수 없는 값은 비우고 needs_review=true 와 이유를 적는다.
4. 근거 구간은 그 행동이 보이거나 말해지는 구간으로 한다.
"""


# 5.4 공공 직무데이터 매칭 ----------------------------------------------------
MATCH_FUNCTIONS = [
    {
        "name": "search_jobcode",
        "description": "장애인 고용직무분류에서 직종명·유사직무명이 비슷한 직종 후보를 찾는다",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
            "required": ["query"],
        },
    },
    {
        "name": "search_ncs_subdivision",
        "description": "NCS 분류체계에서 세분류명이 비슷한 후보와 코드(dutyCd)를 찾는다",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
            "required": ["query"],
        },
    },
    {
        "name": "get_ncs_criteria",
        "description": "세분류 코드의 능력단위·능력단위요소·수행준거를 돌려준다",
        "parameters": {
            "type": "object",
            "properties": {"duty_cd": {"type": "string"}, "comp_unit_cd": {"type": "string"}},
            "required": ["duty_cd"],
        },
    },
    {
        "name": "get_jobcode_tasks",
        "description": "직종코드의 수행업무 설명을 돌려준다",
        "parameters": {
            "type": "object",
            "properties": {"job_cd": {"type": "string"}},
            "required": ["job_cd"],
        },
    },
]


class MatchCodes(BaseModel):
    ncs_duty_cd: str | None
    job_cd: str | None


class Gap(BaseModel):
    source: Literal["NCS", "JOBCODE"]
    criterion: str = Field(description="공공데이터 원문")
    related_step_order: int | None
    gap_type: Literal["missing", "insufficient"]
    note: str


class MatchResult(BaseModel):
    matches: MatchCodes
    gaps: list[Gap]


# 5.5 쉬운 안내문 ------------------------------------------------------------
class EasyText(BaseModel):
    easy_text: str = Field(description="한 문장 한 행동 안내문")
    caution_text: str | None
    source_numbers: list[str] = Field(description="원문에서 옮긴 수치·단위")


# 5.10 질의응답 --------------------------------------------------------------
class Answer(BaseModel):
    answer_text: str
    step_ids: list[int]
    needs_handoff: bool
