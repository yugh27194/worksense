-- 일머RE 초기 스키마 (인계서 6장 DDL 초안 기반)
-- 원칙: 근로자 식별·경계선지능 여부 정보는 저장하지 않는다. 모든 조회는 workplace_id 로 제한한다.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 사업장과 사용자 ------------------------------------------------------------
CREATE TABLE workplaces (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  ctpv_nm TEXT,
  sgg_nm TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE staff_users (            -- 담당자(사업주·교육 담당자·직무지도원)
  id BIGSERIAL PRIMARY KEY,
  workplace_id BIGINT REFERENCES workplaces(id),
  name TEXT,
  role TEXT CHECK (role IN ('owner', 'trainer', 'job_coach')),
  email TEXT UNIQUE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE worker_sessions (        -- 근로자: 이름·장애·경계선지능 정보 저장 금지
  id BIGSERIAL PRIMARY KEY,
  workplace_id BIGINT REFERENCES workplaces(id),
  qr_token TEXT UNIQUE NOT NULL,
  preferences JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 원본 자료와 전사 ------------------------------------------------------------
CREATE TABLE source_media (
  id BIGSERIAL PRIMARY KEY,
  workplace_id BIGINT REFERENCES workplaces(id),   -- 공공 영상은 NULL
  kind TEXT CHECK (kind IN ('public_job_video', 'workplace_video', 'document', 'photo')),
  title TEXT,
  storage_path TEXT NOT NULL,
  duration_ms INT,
  public_data_id TEXT,
  consent_confirmed BOOLEAN DEFAULT false,
  uploaded_by BIGINT REFERENCES staff_users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE transcripts (
  id BIGSERIAL PRIMARY KEY,
  media_id BIGINT REFERENCES source_media(id),
  model TEXT,
  words JSONB NOT NULL,
  text TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 작업 큐: PostgreSQL 기반 (SELECT ... FOR UPDATE SKIP LOCKED)
CREATE TABLE analysis_jobs (
  id BIGSERIAL PRIMARY KEY,
  media_id BIGINT REFERENCES source_media(id),
  stage TEXT,
  status TEXT CHECK (status IN ('queued', 'running', 'done', 'failed')),
  error TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ
);
CREATE INDEX ON analysis_jobs (status, created_at);

-- 매뉴얼: 직무 → 업무 → 단계 ---------------------------------------------------
CREATE TABLE manuals (
  id BIGSERIAL PRIMARY KEY,
  workplace_id BIGINT REFERENCES workplaces(id),
  job_name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE tasks (
  id BIGSERIAL PRIMARY KEY,
  manual_id BIGINT REFERENCES manuals(id),
  name TEXT NOT NULL,
  sort_order INT
);

CREATE TABLE steps (
  id BIGSERIAL PRIMARY KEY,
  task_id BIGINT REFERENCES tasks(id),
  sort_order INT,
  action_source TEXT,                 -- 원본 기준 행동
  easy_text TEXT,
  caution_text TEXT,
  tools TEXT[],
  location TEXT,
  evidence_media_id BIGINT REFERENCES source_media(id),
  evidence_start_ms INT,
  evidence_end_ms INT,
  photo_path TEXT,
  clip_path TEXT,
  location_markup JSONB,
  needs_review BOOLEAN DEFAULT false,
  review_reason TEXT,
  status TEXT CHECK (status IN ('draft', 'in_review', 'approved')) DEFAULT 'draft',
  ai_generated BOOLEAN DEFAULT true,
  version INT DEFAULT 1,
  approved_by BIGINT REFERENCES staff_users(id),
  approved_at TIMESTAMPTZ
);

CREATE TABLE step_revisions (         -- 원본 설명 → AI 안내문 → 담당자 수정본
  id BIGSERIAL PRIMARY KEY,
  step_id BIGINT REFERENCES steps(id),
  version INT,
  source TEXT CHECK (source IN ('ai', 'staff')),
  editor_id BIGINT,
  before JSONB,
  after JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE step_checks (            -- 자동 점검·누락 후보
  id BIGSERIAL PRIMARY KEY,
  step_id BIGINT REFERENCES steps(id),
  check_type TEXT CHECK (check_type IN ('vocab', 'key_info_missing', 'key_info_added',
                                        'ncs_gap', 'jobcode_gap', 'needs_review')),
  payload JSONB,
  resolved BOOLEAN DEFAULT false
);

CREATE TABLE step_refs (
  step_id BIGINT REFERENCES steps(id),
  ref_type TEXT CHECK (ref_type IN ('ncs', 'jobcode')),
  ref_code TEXT,
  ref_text TEXT
);

CREATE TABLE step_embeddings (
  step_id BIGINT PRIMARY KEY REFERENCES steps(id),
  workplace_id BIGINT NOT NULL,
  embedding vector(1536) NOT NULL,
  model TEXT,
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON step_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON step_embeddings (workplace_id);

-- 공공데이터 저장본 ------------------------------------------------------------
CREATE TABLE ncs_classification (
  duty_cd TEXT PRIMARY KEY,
  degr INT,
  l_cd TEXT, l_nm TEXT,
  m_cd TEXT, m_nm TEXT,
  s_cd TEXT, s_nm TEXT,
  d_cd TEXT, d_nm TEXT,
  fetched_at TIMESTAMPTZ
);
CREATE INDEX ON ncs_classification USING gin (d_nm gin_trgm_ops);

CREATE TABLE ncs_comp_units (
  comp_unit_cd TEXT,
  duty_cd TEXT,
  name TEXT,
  definition TEXT,
  level INT,
  PRIMARY KEY (duty_cd, comp_unit_cd)
);

CREATE TABLE ncs_ksa (
  duty_cd TEXT,
  comp_unit_cd TEXT,
  factr_no INT,
  factr_name TEXT,
  gbn_cd TEXT,
  gbn_name TEXT,
  gbn_val TEXT
);

CREATE TABLE jobcodes (
  job_cd TEXT PRIMARY KEY,
  job_cd_nm TEXT,
  job_cd_level TEXT,
  job_task TEXT,
  simlr_job TEXT,
  notice_cn TEXT,
  jobdevtip_cn TEXT,
  fetched_at TIMESTAMPTZ
);
CREATE INDEX ON jobcodes USING gin ((job_cd_nm || ' ' || coalesce(simlr_job, '')) gin_trgm_ops);

CREATE TABLE welfare_services (
  serv_id TEXT PRIMARY KEY,
  source TEXT CHECK (source IN ('central', 'local')),
  serv_nm TEXT,
  summary TEXT,
  ctpv_nm TEXT,
  sgg_nm TEXT,
  intrs_thema TEXT,
  target_text TEXT,
  criteria_text TEXT,
  apply_text TEXT,
  contacts JSONB,
  link TEXT,
  last_mod_ymd TEXT,
  easy_summary TEXT,
  fetched_at TIMESTAMPTZ
);

CREATE TABLE ingest_runs (
  id BIGSERIAL PRIMARY KEY,
  source TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  status TEXT,
  row_count INT,
  error TEXT
);

-- 어휘 점검 ------------------------------------------------------------------
CREATE TABLE vocab_cache (
  lemma TEXT PRIMARY KEY,
  word_grade TEXT,
  fetched_at TIMESTAMPTZ
);

CREATE TABLE field_terms (
  workplace_id BIGINT REFERENCES workplaces(id),
  term TEXT,
  PRIMARY KEY (workplace_id, term)
);

-- 질의응답과 개선 ---------------------------------------------------------------
CREATE TABLE question_logs (
  id BIGSERIAL PRIMARY KEY,
  workplace_id BIGINT NOT NULL,
  worker_session_id BIGINT,
  question_text TEXT,
  question_embedding vector(1536),
  top_similarity REAL,
  matched_step_ids BIGINT[],
  answered BOOLEAN,
  handoff BOOLEAN,
  help_level SMALLINT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE improvement_items (
  id BIGSERIAL PRIMARY KEY,
  step_id BIGINT REFERENCES steps(id),
  question_ids BIGINT[],
  kind TEXT CHECK (kind IN ('repeated', 'unanswered')),
  status TEXT DEFAULT 'open',
  proposed_text TEXT,
  approved_by BIGINT,
  approved_at TIMESTAMPTZ
);
