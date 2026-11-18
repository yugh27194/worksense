# 일머RE MVP 개발 인계서 — 개발용 요약

원본: 「일머RE MVP 개발 인계서」(2026-11-18, 한걸음 팀 데이터 파트). 이 문서는 구현에 필요한 내용만 옮겼다.
절 번호(5.3 등)는 원본 번호이며 코드 주석의 번호와 같다.

표기: **[확정]** 제안서 명시 · **[검증]** 공식 문서·명세·로컬 실행으로 확인 · **[제안]** 인계자 권장안(바꿔도 됨) · **[미결]** `open-questions.md`

## 1. 서비스

- 한 줄 정의: 공공 직무정보와 사업장 교육자료를 AI로 분석해 쉬운 단계별 업무 매뉴얼을 만들고, 업무 중 확인과 질의응답을 지원하는 AI 기반 OJT 보조 서비스.
- 이용자: 카페·음식점·편의점 등 일상 서비스업의 경계선지능 근로자와 일반 신규 근로자.
- 도입 주체: 사업주·교육 담당자, 복지·직업훈련기관의 직무지도원.

## 2. MVP 범위와 일정 [확정]

- 대상 업무: 카페 오픈·마감 등 반복 업무. 담당자용 매뉴얼 관리 화면과 근로자용 모바일 안내·질의응답을 우선 구현.
- 상용 AI API + 공공데이터 + 공개 도구 조합. 기초 모델을 새로 학습시키지 않는다.
- 목표: 기본 사용자 매뉴얼 제작과 질문 응답 구현, **주요 정보 변경 0건 · 근거 없는 답변 0건**.

| 우선순위 [제안] | 기능 |
|---|---|
| P0 (시연 필수) | 영상 업로드·전처리, 음성 전사, 작업 단계 추출, NCS·직무분류 매칭과 누락 점검, 쉬운 안내문 생성, 어휘·주요 정보 자동 점검, 사진·클립 추출, 담당자 검토·승인, 근로자 단계 카드, RAG 질의응답, 단계적 도움, 담당자 연결, AI 생성·승인 표시 |
| P1 | 3~4개 선택 질문으로 안내 방식 설정, 반복 질문 분석과 매뉴얼 개선, 복지서비스 안내 |
| P2 | 데이터 개방용 내보내기(원본 설명 → AI 안내문 → 담당자 수정본), 관리 통계 |

| 일정 | 내용 |
|---|---|
| ~11/22 | 서비스 기획·Figma 디자인 확정, AI 모델 연동 및 핵심 기능 검증 |
| 11/23~29 | 영상 분석, 공공데이터 연계, 매뉴얼 생성·승인, 사용자 화면 및 질의응답 구현 |
| 11/30 | 웹 기반 MVP 배포 및 기능 점검 |
| 12/3 | 본선 MVP 시연 및 발표 |

## 3. 시스템 구성 [제안]

```
[담당자 웹]          [근로자 모바일 웹 (QR 접속)]
      └──────► [API 서버] ◄──────┘
                  │
     ┌────────────┴─────────────┐
[PostgreSQL + pgvector]     [작업 큐 / 워커]
 매뉴얼·단계·이력·로그·벡터     FFmpeg → 전사 → 단계 추출 → 매칭 → 안내문 → 자동 점검 → 사진·클립 → 임베딩
 공공데이터 저장본                    │
      ▲                      [오브젝트 스토리지] 원본 영상, WAV, 대표 사진, 안내 클립
[수집 스케줄러] NCS·직무분류 주 1회, 복지서비스 하루 1회
외부: Gemini API(유료) · 공공데이터포털 API · 한국어기초사전 API
```

영상 분석은 수십 초~수 분이 걸리므로 API 요청 안에서 처리하지 않고 작업 큐로 넘긴다.

### 모델·도구 사양 [검증]

| 대상 | 확인한 사양 | 구현 영향 |
|---|---|---|
| `gemini-3.8-flash` | 입력 텍스트·이미지·영상·오디오·PDF, 입력 1,048,576 / 출력 65,536 토큰. 함수 호출·구조화 출력. 영상 기본 1 FPS, 프롬프트에서 `MM:SS` 시점 지정. 100MB·10분 초과·재사용 파일은 File API 권장 | 영상은 File API 로 올리고 근거 구간을 `MM:SS` 로 받는다 |
| `gemini-3.5-transcribe` | 오디오만(최대 1시간). 단어 타임스탬프는 요청당 30분. ko-KR. 타임스탬프와 사용자 어휘 동시 사용 불가 | MP4에서 음성을 분리해 25분 단위로 나눠 보낸다. 현장 용어는 5.6 단계에서 처리 |
| `gemini-3.5-flash-lite` | 함수 호출·구조화 출력 | 고빈도 작업(안내문 재작성, 답변 생성) |
| `gemini-embedding-2` | 입력 8,192 토큰, 출력 128~3072 (권장 768·1536·3072) | 1,536차원 |
| 구조화 출력 + 함수 호출 | Gemini 3 계열에서 함께 쓰는 기능은 preview | 매칭(함수 호출)과 결과 정리(구조화 출력)를 두 번의 호출로 나눈다 [제안] |
| pgvector | HNSW·IVFFlat 인덱스는 `vector` 2,000차원까지 | 3,072차원 인덱스 불가 → 1,536차원 |
| Kiwi 0.24.1 | 사전에 없는 복합 현장 용어를 쪼갬. `add_user_word` 로 등록하면 한 단어 | 사업장별 현장 용어 사전(`field_terms`) |
| FFmpeg 6.1.1 | `media_commands.sh` 명령 실행 확인 | |

Gemini SDK 의 파라미터 이름(구조화 출력 지정, 임베딩 출력 차원 지정)은 SDK 버전에 따라 다르다. 구현 시점 공식 문서를 기준으로 한다.

## 4. 데이터 소스 [검증]

Swagger 정의로만 확인했다(인증키 없어 실제 호출 안 함). **첫 호출에서 응답 구조를 다시 확인한다.** 공공데이터포털 데이터의 이용허락범위는 모두 '제한 없음'.

| 데이터 | 제공 | 형식 | 수집 | 단계 | 개발계정 한도 |
|---|---|---|---|---|---|
| 누구나 알기쉬운 발달장애인 직업정보 영상 | 한국장애인고용공단 | MP4 파일데이터 | 1회 수동 | 5.1~5.3 | — |
| 국가직무능력표준(NCS) 정보 API (15157547) | 한국산업인력공단 | REST, XML | 주 1회 | 5.4 | 10,000건/일 |
| 장애인 고용직무분류 API (15157071) | 한국장애인고용공단 | REST, XML | 주 1회 | 5.4 | 10,000건/일 |
| 중앙부처 복지서비스 API (15090532) | 한국사회보장정보원 | REST, XML | 하루 1회 | 5.12 | **100건/일** |
| 지자체 복지서비스 API (15108347) | 한국사회보장정보원 | REST, XML | 하루 1회 | 5.12 | 1,000건/일 |
| 한국어기초사전 오픈 API | 국립국어원 | REST, XML | 조회 결과 캐시 | 5.6 | 50,000건/일 |
| 사업장 교육자료 | 서비스 이용 사업장 | 영상·문서·사진 | 업로드 시 | 5.1~5.5 | — |

### 4.1 발달장애인 직업정보 영상
- 공개 직무 24개(휠마스터, 편의점정리원, 클린마스터, 사무보조원, 제과제빵원, 주방보조원, 티마스터, 호텔객실정리원 등). 예: 편의점정리원 15123185, 주방보조원 15123777, 사무보조원 15123014, 티마스터 15123773, 호텔객실정리원 15123776, 자전거정비사 15123463, 샵화디자이너 15123774.
- **카페·바리스타 직무 영상은 없다.** 카페 MVP 는 사업장 영상이 주 입력. 인접 직무: 티마스터, 주방보조원, 제과제빵원.
- 진로 안내용이라 '기본 작업 구조'만 만들고 세부 절차는 사업장 자료로 채운다.

### 4.2 NCS 정보 API
- 호스트 `apis.data.go.kr/B490007/ncsInfo`. 공통 파라미터 `serviceKey`, `numOfRows`, `pageNo`, `returnType`(모두 필수).
- 오류 코드: 999 인증 실패, 002 데이터 없음, 009 필수 파라미터 누락.

| 오퍼레이션 | 용도 | 추가 파라미터 | 주요 응답 필드 |
|---|---|---|---|
| `/ncsCdInfo` | 분류체계 | — | `ncsDegr`, `ncsLclasCd/Nm`, `ncsMclasCd/Nm`, `ncsSclasCd/Nm`, `ncsSubdCd/Nm` |
| `/ncsDutyInfo` | 직무 정보 | `dutyCd` | `dutyCd`, `dutyNm`, `dutySvcNo`, `dutyDef` |
| `/ncsCompeUnitInfo` | 능력단위 | `dutyCd` | `compUnitCd`, `compUnitName`, `compUnitDef`, `compUnitLevel`, `ncsClCd` |
| `/ncsCompeUnitFactrInfo` | 능력단위요소 | (명세 확인) | `compUnitFactrNo`, `compUnitFactrName`, `compUnitCd`, `compUnitName` |
| `/ncsKsaInfo` | 수행준거·KSA | `dutyCd`(필수), `compUnitCd` | `compUnitCd`, `compUnitName`, `compUnitFactrNo`, `compUnitFactrName`, `gbnCd`, `gbnName`, `gbnVal` |

- 키워드 검색이 없다 → `ncsCdInfo` 전체를 저장해 두고 세분류명으로 코드를 찾은 뒤 능력단위·수행준거를 받는다.
- Swagger 에 `compUnitFactrName` 이 number 로 적혀 있으나 문자열로 저장한다.

### 4.3 장애인 고용직무분류 API
- 호스트 `apis.data.go.kr/B552583/jobcode`, 오퍼레이션 `/job_code`. 파라미터 `serviceKey`, `pageNo`, `numOfRows`(모두 필수). 검색 조건 없음 → 전체를 받아 내부에서 검색.
- 응답: `header`(resultCode, resultMsg), `body`(totalCount, numOfRows, pageNo, items.item)
- 필드: `jobCd`(직종코드, 매칭 결과로 저장), `jobCdNm`(직종명), `jobCdLevel`(직종 레벨), `jobTask`(수행업무, 매뉴얼 초안과 대조), `simlrJob`(유사직무명), `noticeCn`(분류 시 주의사항 — 작업 안전 정보 아님, 안내문에 쓰지 않음), `jobdevtipCn`(MVP 미사용), `rnum`.
- Swagger 에서 `jobCdNm` 과 `jobCdLevel` 설명이 서로 바뀌어 있다. 실제 응답으로 확인.

### 4.4 중앙부처 복지서비스 API
- 호스트 `apis.data.go.kr/B554287/NationalWelfareInformationsV001`. **개발계정 하루 100건.**
- `/NationalWelfarelistV001`: `callTp=L`, `pageNo`(최대 1000), `numOfRows`(최대 500), `srchKeyCode`(001 제목, 002 내용, 003 제목+내용), `searchWrd`, `lifeArray`, `trgterIndvdlArray`, `intrsThemaArray`, `age`, `onapPsbltYn`, `orderBy` → `servId`, `servNm`, `servDgst`, `servDtlLink`, `jurMnofNm`, `rprsCtadr`, ...
- `/NationalWelfaredetailedV001`: `callTp=D`, `servId` → `tgtrDtlCn`, `slctCritCn`, `alwServCn`, `rprsCtadr`, `applmetList`, `inqplCtadrList`, `inqplHmpgReldList`, `basfrmList`, `baslawList`

### 4.5 지자체 복지서비스 API
- 호스트 `apis.data.go.kr/B554287/LocalGovernmentWelfareInformations`
- `/LcgvWelfarelist`: `pageNo`, `numOfRows`, `lifeArray`, `trgterIndvdlArray`, `intrsThemaArray`, `age`, `ctpvNm`, `sggNm`, `srchKeyCode`, `searchWrd`, `arrgOrd`
- `/LcgvWelfaredetailed`: `servId` → `sprtTrgtCn`, `slctCritCn`, `alwServCn`, `aplyMtdCn`, `inqplCtadrList`, `inqplHmpgReldList`, `enfcBgngYmd`·`enfcEndYmd`, `lastModYmd`
- 생애주기·가구상황·관심주제 코드는 데이터 상세 페이지의 참고문서(코드표)를 따른다.

### 4.6 한국어기초사전 오픈 API
- `GET https://krdict.korean.go.kr/api/search?key={32자리 인증키}&q={검색어}`
- 등급 필터: `advanced=y` 와 `level`(level1 초급, level2 중급, level3 고급, 기본 all).
- 응답 XML: `channel`(total, start, num) 아래 `item` 에 `target_code`, `word`, `sup_no`, `pos`, `link`, `sense`.
- **`word_grade`(초급·중급·고급)는 선택 필드** — 없으면 '등급 없음'으로 처리.
- 하루 50,000건, 초과 시 오류 코드 010 → `vocab_cache` 로 반복 조회 방지.

### 4.7 사업장 교육자료
- 업무교육 영상, 작업 순서·도구 위치·기기 사용법·안전 수칙 문서와 사진. **촬영 허가·동의를 받은 자료만** 쓴다.
- 사업장별로 저장 공간과 검색 인덱스의 접근 범위를 나눈다.

## 5. AI 파이프라인

각 단계는 입력·처리·출력이 정해져 있어 따로 개발·테스트할 수 있다. 단계 사이 데이터는 DB 테이블에 저장한다.

| 절 | 단계 | 처리 | 코드 |
|---|---|---|---|
| 5.1 | 업로드·전처리 | 원본 저장 → FFmpeg 16kHz 모노 WAV → 25분(1500초) 분할. 분할 전사 결과에 `n × 1500초` 오프셋을 더해 원본 시각으로 | `pipeline/media.py` |
| 5.2 | 음성 전사 | `gemini-3.5-transcribe`, 단어 타임스탬프, ko-KR, 사용자 어휘 미사용 → `transcripts.words = [{start_ms, end_ms, text}]`. 5.3 프롬프트에는 문장 단위로 `[MM:SS] 문장` 형식 [제안] | `worker.stage_transcribe` |
| 5.3 | 작업 단계 추출 | `gemini-3.8-flash` 가 영상(File API) + 시각 표시 전사문 → `StepExtraction` (구조화 출력) | `schemas/llm.py` |
| 5.4 | 공공 직무데이터 매칭·누락 점검 | 함수 호출(`search_jobcode`, `search_ncs_subdivision`, `get_ncs_criteria`, `get_jobcode_tasks`, 서버는 pg_trgm 유사도) → 두 번째 호출에서 `MatchResult` 로 정리. 매칭은 후보일 뿐, 담당자 확인 후 반영. 공공데이터 원문은 고치지 않고 보여 준다 | `schemas/llm.py` |
| 5.5 | 매뉴얼 구성·쉬운 안내문 | 매뉴얼은 '직무 → 업무 → 단계' [확정]. 단계마다 행동 문장·대표 사진·5~10초 안내 영상·주의 사항. `gemini-3.5-flash-lite` 가 '한 문장 하나의 행동' 원칙으로 `EasyText` 출력 | `schemas/llm.py` |
| 5.6 | 자동 점검 (규칙 기반) | ① 현장 용어 Kiwi 사용자 사전 등록 ② 내용어(NNG·NNP·VV·VA·MAG) 기본형 → `word_grade` 대조, 중급·고급·등급 없음은 '검토할 표현'(현장 용어 제외) ③ 원문·안내문의 수치·단위(SN + SL·NNB)·도구명·주의 사항 양방향 비교 → '누락' / '임의 추가' → `step_checks` | `pipeline/easy_text_check.py` ✅ |
| 5.7 | 사진·클립 | 대표 사진: 근거 구간 안 한 시점(기본 중앙 [제안]) JPEG. 안내 클립: 5~10초(짧으면 앞뒤로 늘리고 길면 앞쪽 10초), 소리 제거, faststart. 담당자가 교체 가능 | `pipeline/media.py` ✅ |
| 5.8 | 검토·승인 | 상태 `draft` → `in_review` → `approved`(근로자에게 공개). 화면에 5.3 확인 필요, 5.4 누락 후보, 5.6 검토할 표현·누락·임의 추가를 함께 표시. 수정은 모두 `step_revisions` 에. 승인 시 5.9 실행 | `api/staff.py` |
| 5.9 | 임베딩·인덱싱 | 승인 단계 → `gemini-embedding-2` 1,536차원 → `vector(1536)` + HNSW(cosine). 검색은 반드시 `workplace_id` 와 `status='approved'` 로 거른다. 임베딩 텍스트 [제안]: `업무명 > 단계 n: 쉬운 안내문 / 원본 행동 / 도구 / 위치 / 주의 사항` | `pipeline/gemini.py` |
| 5.10 | 질의응답·단계적 도움 | 질문 임베딩 → top-k(k=3 [제안]) → 최고 유사도가 임계값 미만이면 답을 만들지 않음 → `gemini-3.5-flash-lite` 가 검색된 단계만 컨텍스트로 `Answer` 출력 → `step_ids` 가 비었거나 검색 결과 밖이면 담당자 연결로 교체 → `question_logs` | `pipeline/qa.py` ✅ 안전장치 |
| 5.11 | 반복 질문 분석 | 질문 벡터 코사인 유사도 0.85 이상을 같은 묶음 [제안], 단계별 건수. 보완 설명 승인 → 단계 새 버전 + 재임베딩. 근로자별 통계·능력 평가에 쓰지 않는다 | `pipeline/qa.py` |
| 5.12 | 복지서비스 안내 [미결] | 지역·관심주제(일자리 등) 맞춤 서비스를 쉬운 문장으로. 수급 자격 판정 금지, 원문 링크·문의처 항상 표시 | `api/worker.py` |

단계적 도움 [확정]: 0 간결한 문장 → 1 위치 표시 사진 → 2 작업 영상(5~10초) → 3 더 작은 단위의 설명(Flash-Lite 가 하위 행동 2~3개로 [제안]) → 4 담당자 연결.

5.3 프롬프트 규칙 [제안]:
1. 화면과 전사문에서 직접 확인되는 내용만 쓴다.
2. 한 단계에는 행동 하나만 담는다.
3. 기기 조작법, 수치, 사업장마다 다른 절차처럼 확정할 수 없는 값은 비우고 `needs_review=true` 와 이유를 적는다.
4. 근거 구간은 그 행동이 보이거나 말해지는 구간으로 한다.

## 6~8. DB · API · 화면

- DDL: `backend/migrations/001_init.sql` (인계서 6장 그대로 + `analysis_jobs.created_at`). `worker_sessions` 에는 근로자를 식별하거나 특성을 추정할 정보를 넣지 않는다. 모든 조회에 `workplace_id` 조건을 강제한다(행 수준 보안 적용 검토).
- API: `backend/app/api/` (7장 표와 같은 경로).
- 화면 (Figma 시안 11/22 확정 예정):
  - 담당자 웹: 자료 업로드(촬영 동의 체크) · 분석 진행(전사 → 단계 추출 → 매칭 → 안내문 → 점검 → 사진·클립) · 매뉴얼 검토(원본 행동, 쉬운 안내문, 사진, 클립, 근거 구간 재생, 점검 표시) · 승인(단계별/업무 전체) · 개선 요청 · QR 발급과 현장 용어 관리
  - 근로자 모바일 웹: QR 진입 · 안내 방식 선택(3~4개) · 업무 선택 · 단계 카드(행동 문장, 대표 사진, 5~10초 영상, 주의 사항, 이전·다음) · 질문 → 답변 → '더 도와주세요' → 담당자 연결 · 복지서비스 안내(P1)
  - 모든 AI 생성 내용에 'AI가 만든 내용'과 '담당자 확인 완료' 표시.

## 9. 비기능 요구사항

- **개인정보와 책임 있는 AI [확정]**: 경계선지능 여부 미수집, 이용 기록으로 능력 평가 금지, 사업장별 자료·검색 인덱스 분리, 실제 영상은 입력이 제품 개선에 쓰이지 않는 **Gemini API 유료 환경**에서만 처리, AI 생성물에 생성 사실·승인 여부 표시.
- **안정성 [확정]**: 공공 API 는 주기 수집해 내부 저장. 호출 실패해도 저장본으로 서비스 지속. 단계마다 근거 구간·참고 직무 표준·수정 이력·승인 상태 저장.
- **보안·운영 [제안]**: 키는 환경변수/비밀 관리 도구. 공공데이터포털 키는 URL 쿼리로 가므로 요청 URL 을 로그에 남기지 않는다. 업로드 파일은 서명된 URL 로만 접근. 수집 실패는 `ingest_runs` 에 기록, 연속 실패 시 알림.
- **비용 [확정]**: 무거운 작업(영상 분석)은 3.8 Flash, 자주 호출되는 작업(안내문·답변)은 3.5 Flash-Lite.

## 10. 평가 지표

| 지표 | 정의 [확정] | 측정 방법 [제안] | MVP 목표 |
|---|---|---|---|
| 매뉴얼 1건 제작 시간 | 업무 하나의 매뉴얼을 만드는 데 걸린 시간 | `source_media.created_at` ~ 마지막 `steps.approved_at` | 기록 |
| 작업 단계 누락·순서 오류 비율 | AI 초안이 단계를 빠뜨리거나 순서를 틀린 정도 | 승인본 기준 담당자가 추가한 단계 수 + 순서를 바꾼 단계 수 ÷ 승인본 단계 수 (`step_revisions`) | 기록 |
| 주요 정보 보존율 | 원문의 주요 정보가 안내문에 남은 비율 | 5.6 에서 뽑은 원문 수치·도구명·주의 사항 중 안내문에 보존된 비율 | 주요 정보 변경 0건 |
| 근거 없는 답변 수 | 승인 매뉴얼에 없는 내용을 답한 건수 | 답변 로그 표본 사람 검수 + `step_ids` 검증 자동 차단 | 0건 |

## 11. 모델 대체 옵션 [검증]

| 역할 | 현재 | 대안 |
|---|---|---|
| 영상 분석 | gemini-3.8-flash | TwelveLabs Pegasus 1.5, Amazon Nova 2 Lite, Alibaba Qwen3-VL·Omni |
| 영상 분석(프레임 방식) | — | Claude Sonnet 5.5, OpenAI GPT-6.1 계열, HyperCLOVA X HCX-005 (FFmpeg 장면 이미지 + 전사문) |
| 음성 전사 | gemini-3.5-transcribe | 네이버 CLOVA Speech 장문 인식 |
| 안내문·답변 | gemini-3.5-flash-lite | Claude Haiku 5.5, GPT-6 Luna, HyperCLOVA X HCX-007, Upstage Solar Pro 4 |
| 임베딩 | gemini-embedding-2 | OpenAI text-embedding-3-small, KURE-v1, BGE-M3, Upstage Embedding (바꾸면 전체 재계산) |

모델을 바꾸면 9장의 'Gemini API 유료 환경' 문구와 데이터 처리 정책도 함께 바꿔야 한다.
