-- 제안서 개정판 반영: 버튼형 도움(「다시 보여줘」「더 쉽게」「사진으로」「사람 불러줘」)
-- '더 쉽게' 안내문은 일괄 생성 때 미리 만들어 저장한다 (런타임 AI 호출 없음).
ALTER TABLE steps ADD COLUMN easier_text TEXT;
ALTER TABLE manuals ADD COLUMN source_job_key TEXT;

-- 도움 요청 기록: 근로자 세션을 저장하지 않고 단계별 합계로만 쓴다 (능력 평가 금지, 인계서 9.1).
CREATE TABLE help_events (
  id BIGSERIAL PRIMARY KEY,
  workplace_id BIGINT NOT NULL,
  step_id BIGINT REFERENCES steps(id),
  kind TEXT CHECK (kind IN ('repeat', 'easier', 'photo', 'handoff', 'done')),
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON help_events (workplace_id, step_id);
