"""Gemini 구조화 출력 스키마와 함수 호출 정의 (인계서 5.3·5.4·5.5·5.10).

Pydantic 모델을 구조화 출력의 response_schema 로 넘기고, 응답도 같은 모델로 검증한다.
Gemini SDK 파라미터 이름은 버전마다 다르므로 호출부(app/pipeline/gemini.py)에 모아 둔다.
"""
from typing import Literal

from pydantic import BaseModel, Field


# 5.2 음성 전사 -------------------------------------------------------------
class TranscriptSegment(BaseModel):
    start: str = Field(description="문장 시작 시각 MM:SS (이 오디오 조각 기준)")
    end: str = Field(description="문장 끝 시각 MM:SS (이 오디오 조각 기준)")
    text: str = Field(description="들리는 그대로의 한국어 문장")


class Transcript(BaseModel):
    segments: list[TranscriptSegment]


TRANSCRIBE_PROMPT = """\
이 한국어 오디오를 문장 단위로 빠짐없이 받아 적는다.
- 들리는 말만 적고, 요약하거나 고치지 않는다.
- 각 문장의 시작·끝 시각을 MM:SS 로 적는다.
- 배경 음악·효과음만 있는 구간은 적지 않는다.
"""


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


class TaskExtraction(BaseModel):
    """한 영상에 업무(task)가 여러 개일 수 있다. 매뉴얼 구조: 직무 → 업무 → 단계 (5.5)."""
    tasks: list[StepExtraction]


EXTRACTION_RULES = """\
1. 화면과 전사문에서 직접 확인되는 내용만 쓴다.
2. 한 단계에는 행동 하나만 담는다.
3. 기기 조작법, 수치, 사업장마다 다른 절차처럼 확정할 수 없는 값은 비우고 needs_review=true 와 이유를 적는다.
4. 근거 구간은 그 행동이 보이거나 말해지는 구간으로 한다.
"""

EXTRACTION_PROMPT = """\
이 영상은 '{job_name}' 직무를 소개하는 교육 영상이다. 영상 화면과 아래 시각 표시 전사문을 함께 보고,
근로자가 실제로 하는 업무를 업무(task)별로 나누고, 업무마다 작업 단계(steps)를 순서대로 뽑는다.
직무 소개·인터뷰·소감처럼 작업 행동이 아닌 구간은 단계로 만들지 않는다.

규칙
{rules}
전사문
{transcript}
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
    code: str | None = Field(default=None, description="원문이 나온 코드 (원문 '### [코드 이름]' 제목의 코드)")
    criterion: str = Field(description="공공데이터 원문")
    related_step_order: int | None
    gap_type: Literal["missing", "insufficient"]
    note: str


class MatchResult(BaseModel):
    matches: MatchCodes
    gaps: list[Gap]


class GapReport(BaseModel):
    """직무 코드를 사람이 확정한 경우(notebooks/02)에는 함수 호출 없이 공공데이터 원문을 바로 넣어 누락만 찾는다."""
    gaps: list[Gap]


GAP_PROMPT = """\
아래는 AI 가 영상에서 뽑은 '{job_name}' 작업 단계와, 이 직무의 공공 직무데이터 원문이다.
공공데이터 원문의 수행업무·수행준거 중 작업 단계에 없거나(missing) 설명이 부족한(insufficient) 항목을 찾는다.
- criterion 에는 공공데이터 원문 문장을 고치지 말고 그대로 옮긴다.
- 영상 직무 범위와 무관한 항목(관리·교육·경영 등)은 제외한다.
- 관련 단계가 있으면 related_step_order 에 그 order 를, 없으면 null.
- 원문은 코드별로 '### [코드 이름]' 제목 아래 묶여 있다. 항목이 나온 코드를 code 에 적는다.

작업 단계
{steps}
장애인 고용직무분류 수행업무 (JOBCODE)
{jobcode}
NCS 수행준거 (NCS)
{ncs}
"""


# 5.5 쉬운 안내문 ------------------------------------------------------------
class EasyText(BaseModel):
    easy_text: str = Field(description="한 문장 한 행동 안내문")
    caution_text: str | None
    source_numbers: list[str] = Field(description="원문에서 옮긴 수치·단위")


class EasyTextItem(EasyText):
    order: int
    easier_text: str = Field(description="「더 쉽게」 버튼용: 더 짧고 더 쉬운 낱말로 쓴 같은 행동")


class EasyTextBatch(BaseModel):
    items: list[EasyTextItem]


EASY_PROMPT = """\
경계선지능 근로자가 읽을 작업 안내문을 쓴다. 아래 작업 단계 하나마다 안내문을 만든다.
원칙 (국내 발달장애인 읽기 쉬운 자료 연구, W3C 인지·학습 접근성 가이드라인 참고)
- 원문 문장을 옮겨 적지 말고 새로 쓴다. 어미만 바꾼 문장은 실패다.
- 모든 문장은 해요체로 끝낸다 ('~해요', '~넣어요', '~닦아요'). '~합니다', '~한다' 는 쓰지 않는다.
- 한 문장에 하나의 행동만 쓴다. 문장은 짧게, 주어 없이 '무엇을 + 어떻게 해요' 순서로 쓴다.
- 어려운 한자어·문어체는 일상 말로 바꾼다. 예: 착용하다→입다·쓰다, 작동시키다→켜다·누르다, 적재하다→쌓다,
  분류하다→나누다, 손질하다→다듬다, 일정한→같은, 사용하여→~로, 완료된→다 된, 식기→그릇, 등→(빼거나 하나씩 적기).
- 현장 도구 이름(입력의 '도구' 칸에 있는 말)은 easy_text·easier_text 모두에서 글자 그대로 쓴다. 줄이거나 바꾸지 않는다.
- 원문의 수치·단위·주의 사항은 빠뜨리거나 바꾸거나 새로 지어내지 않는다.
- easy_text: 기본 안내문. 한 문장.
- easier_text: easy_text 보다 더 짧고 더 쉬운 낱말로 쓴 같은 행동.
  행동이 둘이면 아주 짧은 두 문장으로 나눈다. 도구 이름은 그대로 둔다.
- caution_text: 입력의 '주의 사항' 칸에 내용이 있을 때만, 그것을 쉬운 말 한 문장으로.
  행동을 다시 쓰지 않는다. 없으면 null.
- source_numbers: 원문에 있는 수치·단위를 그대로 옮긴다. 없으면 빈 목록.

예시 (형식만 참고, 내용은 아래 단계에서 가져온다)
원문: 계량컵을 사용하여 우유 200ml를 계량한 후 스팀피처에 투입한다.
도구: 계량컵, 스팀피처 | 주의: 우유는 냉장 보관된 것을 사용한다
easy_text: 계량컵으로 우유 200ml를 재서 스팀피처에 부어요.
easier_text: 계량컵으로 우유 200ml를 재요. 스팀피처에 넣어요.
caution_text: 냉장고에 있던 우유를 써요.
source_numbers: ["200ml"]

작업 단계 (order, 행동, 도구, 위치, 주의 사항)
{steps}
"""

# 자동 점검(수치·도구명·해요체)에 걸린 단계만 다시 만들 때 EASY_PROMPT 뒤에 붙인다
EASY_RETRY_NOTE = """
지난번 안내문에서 아래 문제가 나왔다. 위 원칙을 지키면서 이 문제를 고쳐 다시 쓴다.
{problems}
"""


# 5.10 질의응답 --------------------------------------------------------------
class Answer(BaseModel):
    answer_text: str
    step_ids: list[int]
    needs_handoff: bool
