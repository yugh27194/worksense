# 미결·확인 필요 사항 (인계서 12장)

코드에서 `12장 #N` 으로 표시한 TODO 가 아래 항목을 가리킨다. 결정되면 이 표를 갱신하고 해당 TODO 를 정리한다.

| # | 항목 | 내용 | 필요 시점 | 코드 위치 |
|---|---|---|---|---|
| 1 | 안내 방식 선택 질문 | 3~4개 문항과 선택지, 선택에 따라 바뀌는 화면 요소 | 11/22 Figma 전 | `frontend/app/w/[token]`, `PUT /w/session/preferences` |
| 2 | 안내문 문체·길이 | 해요체/합니다체, 문장 길이 기준, 사진·문장 배치 | 11/22 | `pipeline` 5.5 프롬프트 |
| 3 | 위치 표시 사진 | 담당자가 사진 위에 표시 vs 자동 생성 | 11/23 | `POST /steps/{id}/media`, `steps.location_markup` |
| 4 | 담당자 연결 채널 | 앱 내 알림 / 문자 / 메신저 | 11/23 | `POST /w/handoff` |
| 5 | 음성 안내 | '글·이미지·음성·영상' 중 음성(TTS) 도구 없음 | 발표 전 | — |
| 6 | 복지서비스 안내 | MVP·시연 포함 여부, '일자리' 관심주제 코드, 중앙부처 API 운영계정 신청 | 11/23 | `GET /w/welfare`, `ingest/data_go_kr.py` |
| 7 | NCS 매칭 | 카페(바리스타) 세분류 코드 확정, `ncsKsaInfo.gbnName` 값 확인 | 첫 API 호출 | `ingest/data_go_kr.py` |
| 8 | 직무분류 매칭 | 카페 관련 직종 존재 여부, `jobCdNm`·`jobCdLevel` 설명 확인 | 첫 API 호출 | `ingest/data_go_kr.py` |
| 9 | 시연 데이터 | 시범 카페 오픈·마감 영상 촬영과 동의 확보 (공공 영상에 카페 직무 없음) | 11/25 | — |
| 10 | 임베딩·검색 | 차원 축소 시 정규화 필요 여부, 유사도 임계값, 반복 질문 묶음 기준값 보정 | 구현 중 | `pipeline/gemini.py`, `.env` `RAG_*` |
| 11 | 개발 환경 | 백엔드·프론트엔드 프레임워크, 호스팅, 오브젝트 스토리지 | 11/22 | 본 저장소는 FastAPI + Next.js 로 시작. 호스팅·스토리지 미정 |
| 12 | 기획서 그림 | 3장 1) 도구 표 FFmpeg 행 '음성 분리' 추가, Transcribe 행 문구, 4장 1) 'WORK EASY' → '일머RE' | 제출 전 | (문서) |
| 13 | 데이터 개방 동의 | 원본·AI·수정본 자료의 이용 동의와 비식별 절차 | MVP 이후 | `step_revisions` |
| 14 | 인증키 | 공공데이터포털 4종, 한국어기초사전, Gemini 유료 키 발급 | 즉시 | `.env.example` |

## 인계서 대비 이 저장소에서 정한 것 (제안 → 구현 선택)

- 비동기 작업: Celery·RQ 대신 **PostgreSQL 기반 큐**(`analysis_jobs` + `FOR UPDATE SKIP LOCKED`). 인프라 추가 없이 시작하기 위함. 이를 위해 `analysis_jobs.created_at` 컬럼을 추가했다.
- DB 접근: ORM 없이 psycopg 3 + SQL. DDL 초안을 그대로 쓰기 위함.
- `GET /jobs/{id}` 의 `id` 는 `media_id` 로 받아 해당 영상의 단계별 작업 상태를 모두 돌려준다.
- 인증: 미구현. 개발 중에는 담당자는 `X-Workplace-Id`, 근로자는 `X-Worker-Token`(QR 토큰) 헤더를 쓴다.
