# 오늘의 프로토타입 진행 방식

목표: 공공 직업정보 영상 1개 직무로 **수집 → AI 매뉴얼 생성 → 검수 → 근로자 화면**까지 한 바퀴 돌린다. 시간이 남으면 2번째 직무.

## 오늘 범위

| 포함 | 미룸 |
|---|---|
| 직무 1개(권장: 주방보조원 15123777) 일괄 생성 | 사업장 영상 업로드 화면 |
| 전사 → 단계 추출 → NCS·직종 매칭 → 쉬운 안내문 + 더 쉬운 안내문 → 자동 점검 → 사진·클립 | 담당자 로그인 |
| 검수는 CSV(노트북·엑셀)로 | 담당자 웹 검수 화면 |
| 근로자 화면: QR 진입 → 업무 선택 → 한 화면 한 단계 → 「다시 보여줘」「더 쉽게」「사진으로」「사람 불러줘」 | 복지서비스 안내 |
| 평가 지표 계산 | 자유 질문 RAG·음성 듣기 (여유 있으면) |

## 역할

- **데이터 담당:** `data/curated/`, `data/gold/`, `notebooks/`, `docs/data-report.md`, 검수 열(`decision`, `edited_easy_text`, `reviewer_note`)
- **Claude:** `backend/`, `frontend/`, 파이프라인이 만드는 `data/review/<job_key>/` 파일

같은 파일을 둘이 고치지 않으므로 `main` 에 바로 올려도 충돌이 거의 없다. 올리기 전에 항상 `git pull`.
노트북은 출력 셀을 지우고 커밋한다(Jupyter: Edit → Clear Outputs of All Cells).

## 주고받는 파일

| 파일 | 만드는 쪽 | 쓰는 쪽 |
|---|---|---|
| `data/raw/api/jobcode.csv`, `ncs_classification.csv` | 01 노트북 | 02 노트북, 매칭 단계 |
| `data/curated/jobs.csv` | 02 노트북 | 파이프라인 전체 |
| 직무 영상 MP4 | 데이터 담당이 내려받아 채팅으로 전달 (git 제외) | 파이프라인 |
| `data/review/<job_key>/transcript.csv` | 파이프라인 | 03 노트북 |
| `data/curated/field_terms.csv`, `vocab_overrides.csv` | 03 노트북 | 자동 점검 |
| `data/gold/<job_key>.csv` | 03 노트북(영상 보며 작성) | 평가 |
| `data/review/<job_key>/steps_review.csv` + 사진·클립 | 파이프라인 | 04 노트북 검수 → 근로자 화면 |

## 단계별 진행

| 단계 | 데이터 담당 (노트북) | Claude | 넘어가는 조건 |
|---|---|---|---|
| 0. 준비 | 저장소 clone, 환경 설치, `.env` 에 `DATA_GO_KR_KEY` | Gemini 키 받기, 일괄 생성 명령 뼈대 | 양쪽 환경 동작 |
| 1. 원천 수집 | `01_collect_api` → API CSV 커밋 | 전사·단계 추출 단계 구현 | CSV 2개 커밋 |
| 2. 직무 확정 | `02_explore_and_map` → `jobs.csv` 커밋, MP4 전달 | 매칭·안내문·점검 단계 구현 | `python -m app.data_check` 통과 + 영상 도착 |
| 3. 전사·기준 답 | `03_gold_and_terms` → 기준 답·현장 용어 커밋 (기준 답은 영상만 보고 먼저 시작 가능) | 영상 전처리·전사 실행 → `transcript.csv` 커밋 | 전사문 커밋 |
| 4. 매뉴얼 생성 | (기준 답 계속) | 단계 추출 ~ 사진·클립 실행 → `steps_review.csv` 커밋, 근로자 화면 작업 | 검토표 커밋 |
| 5. 검수 | `04_review_and_eval` 상단 → 검수 열 채워 커밋 | 근로자 화면 완성 | 검수 커밋 |
| 6. 반영·평가 | `04` 하단 평가 실행, 결과를 `data-report.md` 에 | 승인 단계 DB 반영 → 화면에서 확인 | 근로자 화면에 승인 단계 표시 |
| 7. 시연 점검 | 근로자 입장에서 처음부터 끝까지 써 보기 | 발견된 문제 수정 | 한 바퀴 완료 |

## 0단계 환경 설치 (데이터 담당 로컬)

```bash
git clone https://github.com/yugh27194/worksense.git
cd worksense
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e "backend[notebook]"
cp .env.example .env               # DATA_GO_KR_KEY, KRDICT_KEY 채우기 (커밋 금지)
jupyter lab notebooks/
```

표 형식 검사 (커밋 전에):

```bash
cd backend && python -m app.data_check
```
