# 클라우드 세션 인계 (2026-11-25)

새 Claude 세션이 이어서 할 일. 진행 방식 전체는 `docs/workflow.md`.

## 현재 상태

- 일괄 생성 파이프라인(`app.batch`), 검수 반영(`app.importer`), 버튼형 근로자 화면 완료. 가짜 Gemini 로 전체 흐름 테스트 통과.
- 시연 직무: 주방보조원 (`kitchen_helper`, 공공데이터 15123777, 약 5분, 403MB). `data/curated/jobs.csv` 에 후보 행 있음, 코드 칸은 데이터 담당이 02 노트북으로 채움.
- 환경 `seatsync-worksense`: data.go.kr·apis.data.go.kr·krdict 허용, `GEMINI_API_KEY` 환경 변수, 설정 스크립트(백엔드 venv·프론트 npm ci·pgvector 설치).
- 실제 Gemini 호출은 아직 한 번도 안 했다. 첫 실행에서 모델 이름·구조화 출력 동작을 확인할 것.

## 2026-11-25 실행 결과

- 영상 받음(403,230,553바이트, 5분 2초). 연결이 끊기면 같은 쿠키로 check-limit 부터 다시 호출하면 된다.
- `gemini-3.5-transcribe` 는 이 키로 404 → `GEMINI_MODEL_TRANSCRIBE=gemini-3.8-flash` 로 실행 (open-questions #15).
- 전사 73문장, 업무 4개·단계 7개, 사진·클립 7쌍. `match` 는 jobs.csv 코드가 없어 건너뜀, `KRDICT_KEY` 가 없어 어휘 등급 점검도 건너뜀.
- 사진·클립은 `data/work/kitchen_helper/media/` (git 제외) 에만 있다. 새 세션은 영상부터 다시 받아 `--from assets` 로 다시 만들어야 한다.
- 첫 실행의 `easy_text` 가 원문 어미만 바꾼 수준이라 EASY_PROMPT 를 보강(해요체 강제, 낱말 바꾸기 예, 도구 이름 유지)하고 다시 생성했다.
  세 번 돌려 보니 해요체·쉬운 낱말은 안정적이나 `easier_text` 에서 도구 이름이 빠지는 경우가 남아, 자동 점검이 `easier_text` 도 검사하게 했다('더 쉽게 문장 …' 경고).
  이어서 `stage_easy` 가 수치·도구명 누락·해요체 아님(기계 판정 가능한 것만) 단계만 문제를 알려 주고 최대 2번 다시 만들게 했다(문제가 줄어든 결과만 받음). 실제 실행: 1단계 재생성 → 경고 0.
  부작용: 도구 이름을 지키다 보니 1~3번은 `easier_text` 가 `easy_text` 와 같다.
- 단계 7개는 작업 장면(약 1분 15초)에 비해 적당해 보이나 기준 답과 비교 필요.

- 공공 API 첫 호출(키는 사용자가 채팅으로 줘서 scratchpad 에만 둠, 환경 변수 아님 → 새 세션은 키를 다시 받아야 함).
  `jobcode.csv`·`ncs_classification.csv`·NCS 13010100/13010101 능력단위·수행준거 커밋. 응답 형식 차이로 `data_go_kr.py` 수정, 연결 끊김 재시도 추가.
- `jobs.csv` 확정: 사용자 결정으로 후보 코드 전부 포함(직종 4개, NCS 2개, `;` 구분). `public_reference` 가 코드별로 묶고 NCS 는 수행준거만 쓴다.
  match 결과 누락 후보 8건(모두 단계에 연결). 코드별 정리는 `docs/data-report.md`.
- 어휘 등급 점검 실행: '중급' 도 어려운 낱말로 잡혀 7단계 모두 경고. `field_terms.csv`·`vocab_overrides.csv` 정리 필요(데이터 담당 3번 작업).

## 이어서 할 일

1. 키 확인: `test -n "$GEMINI_API_KEY"` (값은 출력하지 않는다)
2. 영상 받기 (git 에 없음). 사이트의 다운로드 단추와 같은 순서로 호출한다. 자동입력방지 문자를 요구하면 멈추고 사용자에게 받는다.
   - `POST https://www.data.go.kr/tcs/dss/selectFileDataDownload.do` (publicDataPk=15123777,
     publicDataDetailPk=uddi:4f0c4064-a5f6-4d51-a695-a61a250e7ffe, fileDetailSn=1, publicDataTyCode=PR0051) → atchFileId
   - `POST /cmm/cmm/check-limit.json` (atchFileId, fileDetailSn) → `needCaptcha:false` 확인
   - `GET /cmm/cmm/fileDownload.do?atchFileId=…&fileDetailSn=1&dataNm=…` → `data/raw/media/kitchen_helper.mp4`
     (이어받기 미지원, 약 11분. 백그라운드로 `-m 1800`)
   - 이 세션에서는 자동 권한 검사가 check-limit 호출을 막아, 사용자가 권한 모드를 바꾼 뒤 승인했다.
3. `cd backend && .venv/bin/python -m app.batch all kitchen_helper` → `data/review/kitchen_helper/transcript.csv`, `steps_review.csv` 커밋·push
4. 데이터 담당이 `jobs.csv` 코드를 채우면 `python -m app.batch match kitchen_helper` 후 `export` 다시
5. 검수 커밋이 오면: 로컬 Postgres + `python -m app.batch import kitchen_helper` → API·프론트 띄워 근로자 화면 확인

## 로컬 Postgres (Docker 없음)

```bash
P=/var/tmp/ws-pg; mkdir -p $P && chown postgres $P
su postgres -c "/usr/lib/postgresql/16/bin/initdb -D $P/data -A trust -U worksense"
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D $P/data -o '-p 5433 -k $P' -l $P/log start"
psql -h $P -p 5433 -U worksense -d postgres -c "CREATE DATABASE worksense"
for f in backend/migrations/*.sql; do psql -h $P -p 5433 -U worksense -d worksense -v ON_ERROR_STOP=1 -f $f; done
export DATABASE_URL="postgresql://worksense@/worksense?host=$P&port=5433"
```
