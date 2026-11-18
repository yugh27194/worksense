# CLAUDE.md

일머RE: 경계선지능 근로자를 위한 AI OJT 서비스 MVP. 기준 문서는 `docs/handover.md`, 미결 사항은 `docs/open-questions.md`.
코드 주석의 `5.3`, `12장 #7` 같은 번호는 인계서 절 번호다.

## 명령

- 백엔드 테스트: `cd backend && pytest -q` (DB 통합 테스트는 `TEST_DATABASE_URL` 지정 시)
- 백엔드 린트: `cd backend && ruff check .`
- API 서버: `cd backend && uvicorn app.main:app --reload`
- 워커: `cd backend && python -m app.worker`
- 프론트: `cd frontend && npm run dev` / `npm run build`
- DB: `docker compose up -d db` (migrations/*.sql 자동 적용)

## 반드시 지킬 규칙

- 근로자 식별 정보·경계선지능 여부·장애 정보를 저장하지 않는다. `worker_sessions` 에는 안내 방식 설정값만.
- 모든 쿼리에 `workplace_id` 조건. 근로자 화면·검색은 `steps.status = 'approved'` 만.
- 질의응답은 검색된 승인 단계만 근거로 답한다. `app.pipeline.qa.validate_answer` 를 우회하지 않는다.
- 확정할 수 없는 값은 추정하지 말고 `needs_review=true` 로 표시한다.
- AI 생성물에는 'AI가 만든 내용'·'담당자 확인 완료' 표시.
- API 키는 환경변수로만. 공공데이터포털 요청 URL(키 포함)을 로그에 남기지 않는다.
- Gemini SDK 파라미터는 `app/pipeline/gemini.py` 에만 둔다.
- 기획서 원본 HWP(참가신청서 개인정보 포함)는 커밋하지 않는다.
- DB 스키마 변경은 새 파일 `backend/migrations/00N_*.sql` 로 추가한다.
