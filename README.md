# 일머RE (worksense)

> 경계선지능 근로자를 위한 AI OJT 서비스 — 2026 사회보장 데이터를 활용한 AI 혁신 아이디어 경진대회 · 팀 한걸음

공공 직무정보와 사업장 교육자료를 AI로 분석해 **쉬운 단계별 업무 매뉴얼**을 만들고,
업무 중 **확인과 질의응답**을 지원하는 AI 기반 OJT 보조 서비스입니다.

- MVP 대상 업무: 카페 오픈·마감 등 반복 업무
- 일정: **11/30 웹 MVP 배포**, 12/3 본선 시연
- 기준 문서: [`docs/handover.md`](docs/handover.md) (일머RE MVP 개발 인계서 요약)

## 처리 흐름

```
업무교육 영상 업로드 → AI 작업 분석 → 공공데이터 매칭·점검 → 쉬운 매뉴얼·이미지 생성 → 담당자 검토·승인 → 근로자 안내·AI 질의응답
     (5.1)            (5.2·5.3)         (5.4)                 (5.5~5.7)              (5.8)              (5.9~5.11)
```

## 구현 시 반드시 지킬 원칙

1. 공공데이터는 정답이 아니라 근거와 점검 기준으로 쓴다. AI는 후보를 제시하고, 결정은 담당자가 한다.
2. AI가 만든 매뉴얼은 담당자가 **승인하기 전에는 근로자에게 보이지 않는다**.
3. 질의응답은 승인된 매뉴얼에서 찾은 근거로만 답한다. 근거가 없으면 답을 만들지 않고 담당자에게 연결한다.
4. 화면과 음성으로 확인할 수 없는 값은 추정하지 않고 '확인 필요'로 표시한다.
5. 경계선지능 여부를 수집하지 않고, 이용 기록으로 근로자의 능력을 평가하지 않는다.
6. 전 직원이 함께 쓰는 OJT로 설계해 특정 근로자가 지원 대상으로 드러나지 않게 한다.
7. AI 생성물에는 생성 사실과 담당자 승인 여부를 표시한다 (「인공지능 기본법」 투명성 의무).

## 저장소 구조

```
backend/                 Python · FastAPI
  app/main.py            API 서버 진입점
  app/api/               staff.py(담당자) · worker.py(근로자 /w) · internal.py(수집)
  app/pipeline/          media(FFmpeg) · gemini · easy_text_check(Kiwi) · qa(RAG 안전장치)
  app/ingest/            공공데이터포털 · 한국어기초사전 수집기
  app/schemas/llm.py     Gemini 구조화 출력 스키마 · 함수 호출 정의
  app/worker.py          분석 작업 워커 (PostgreSQL 큐, 5.1→5.7 단계)
  migrations/            DDL (PostgreSQL + pgvector + pg_trgm)
  scripts/               media_commands.sh · easy_text_demo.py (인계서 첨부)
  tests/
frontend/                Next.js (모바일 우선)
  app/staff/             담당자 웹
  app/w/[token]/         근로자 모바일 웹 (QR 진입)
docs/                    인계서 요약 · 미결 사항
docker-compose.yml       로컬 PostgreSQL + pgvector
```

## 기술 스택

| 영역 | 내용 |
|---|---|
| 영상 분석·단계 추출·매칭 | Gemini 3.8 Flash (`gemini-3.8-flash`) |
| 음성 전사 | Gemini 3.5 Transcribe (`gemini-3.5-transcribe`) |
| 안내문 재작성·답변 생성 | Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) |
| 임베딩 | Gemini Embedding 2 (`gemini-embedding-2`, 1,536차원) |
| 형태소 분석 / 어휘 등급 | Kiwi (`kiwipiepy`) / 국립국어원 한국어기초사전 API |
| 미디어 처리 | FFmpeg |
| DB·벡터 검색 | PostgreSQL + pgvector (HNSW) + pg_trgm |
| 백엔드 / 프론트엔드 | Python FastAPI / Next.js (React) |
| 비동기 작업 | PostgreSQL 기반 큐 (`FOR UPDATE SKIP LOCKED`) |

## 로컬 실행

사전 준비: Python 3.11+, Node 22+, FFmpeg, Docker

```bash
cp .env.example .env   # 키 채우기 (커밋 금지)
docker compose up -d db
```

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload       # http://localhost:8000/docs
python -m app.worker                # 다른 터미널에서 분석 워커
```

```bash
cd frontend
npm install
npm run dev                         # http://localhost:3000
```

개발용 사업장 만들기:

```bash
docker compose exec db psql -U worksense -c "INSERT INTO workplaces (name) VALUES ('시범 카페')"
```

## 테스트

```bash
cd backend && pytest -q
```

DB 통합 테스트까지 돌리려면 `TEST_DATABASE_URL=postgresql://worksense:worksense@localhost:5432/worksense`를 지정합니다.

## 인증키 (12장 #14)

| 키 | 발급처 | 환경변수 |
|---|---|---|
| 공공데이터포털 4종 (NCS 15157547, 장애인 고용직무분류 15157071, 중앙부처 복지 15090532, 지자체 복지 15108347) | data.go.kr | `DATA_GO_KR_KEY` |
| 한국어기초사전 오픈 API | krdict.korean.go.kr | `KRDICT_KEY` |
| Gemini API (**유료 환경**) | Google AI Studio | `GEMINI_API_KEY` |

공공데이터포털 키는 URL 쿼리로 전달되므로 요청 URL을 로그에 남기지 않습니다.

## 진행 현황

| 단계 | 상태 |
|---|---|
| DB 스키마 (6장) | ✅ |
| API 골격 (7장) | ✅ 업로드·분석 등록·진행 상태·매뉴얼 조회·QR·근로자 세션 / ⏳ 수정·승인·질의응답 |
| 5.1 전처리 · 5.7 사진·클립 | ✅ FFmpeg 함수 / ⏳ 워커 연결 |
| 5.2 전사 · 5.3 단계 추출 · 5.4 매칭 · 5.5 안내문 | ⏳ 스키마·함수 정의 완료, 호출 구현 필요 |
| 5.6 자동 점검 | ✅ |
| 5.9 임베딩 · 5.10 질의응답 | ⏳ 근거 검증 안전장치 완료 |
| 공공데이터 수집기 | ⏳ 클라이언트 완료, 첫 호출로 응답 구조 확인 필요 |
| 담당자·근로자 화면 | ⏳ 최소 화면, Figma 시안(11/22) 반영 필요 |

미결 사항은 [`docs/open-questions.md`](docs/open-questions.md), 오늘의 진행 방식은 [`docs/workflow.md`](docs/workflow.md)에 있습니다.
