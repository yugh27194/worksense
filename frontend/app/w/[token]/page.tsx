"use client";

// 근로자 모바일 웹 (인계서 8장): 1 QR 진입 → 2 안내 방식 선택 → 3 업무 선택 → 4 단계 카드 → 5 질문·단계적 도움 → 6 복지(P1)
// 근로자를 식별하는 정보는 받지 않는다. 승인된 단계만 보인다.
import { use, useEffect, useState } from "react";
import { AiBadges } from "@/components";
import { API_BASE, workerFetch } from "@/lib/api";

type TaskRow = { manual_id: number; job_name: string; task_id: number; task_name: string };
type Step = {
  id: number;
  easy_text: string;
  caution_text: string | null;
  photo_path: string | null;
  clip_path: string | null;
  ai_generated: boolean;
  approved_at: string | null;
};

export default function WorkerPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [idx, setIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/w/${token}`)
      .then((r) => {
        if (!r.ok) throw new Error("QR이 올바르지 않아요. 담당자에게 물어보세요.");
        return workerFetch("/w/manuals", token);
      })
      .then(setTasks)
      .catch((e) => setError(String(e.message ?? e)));
  }, [token]);

  async function openTask(taskId: number) {
    setSteps(await workerFetch(`/w/tasks/${taskId}`, token));
    setIdx(0);
  }

  if (error) return <main><p className="warn">{error}</p></main>;

  if (steps.length === 0) {
    return (
      <main>
        <h1>오늘 할 일</h1>
        {/* TODO: 안내 방식 선택 질문 3~4개 (12장 #1 미결) */}
        {tasks.length === 0 && <p>아직 준비된 업무가 없어요.</p>}
        {tasks.map((t) => (
          <div className="card" key={t.task_id}>
            <button onClick={() => openTask(t.task_id)}>{t.task_name}</button>
          </div>
        ))}
      </main>
    );
  }

  const s = steps[idx];
  return (
    <main>
      <p>
        {idx + 1} / {steps.length}
      </p>
      <div className="card">
        <p style={{ fontSize: 22 }}>{s.easy_text}</p>
        {s.caution_text && <p className="warn">조심: {s.caution_text}</p>}
        {/* TODO: 대표 사진·5~10초 클립 — 서명된 URL 로 제공 (9.3) */}
        <AiBadges aiGenerated={s.ai_generated} approvedAt={s.approved_at} />
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={() => setIdx(Math.max(0, idx - 1))} disabled={idx === 0}>
          이전
        </button>
        <button onClick={() => setIdx(Math.min(steps.length - 1, idx + 1))} disabled={idx === steps.length - 1}>
          다음
        </button>
        <button onClick={() => setSteps([])}>업무 목록</button>
      </div>
      {/* TODO: 질문 입력 → /w/ask, '더 도와주세요' → /w/ask/{id}/more-help, 담당자 연결 → /w/handoff */}
    </main>
  );
}
