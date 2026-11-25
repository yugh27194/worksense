"use client";

// 근로자 모바일 웹 (제안서 6장 2) 당사자 사용성 설계)
// - 한 화면에 한 단계, 화면 구조 고정
// - 문장 입력 대신 「다시 보여줘」「더 쉽게」「사진으로」「사람 불러줘」 단추
// - 손이 젖었거나 물건을 든 상황: 「소리로 듣기」(브라우저 음성 합성)
// - 단추 요청은 저장된 매뉴얼을 다시 보여 줄 뿐 AI 를 부르지 않는다. 근로자를 식별하는 정보는 받지 않는다.
import { use, useCallback, useEffect, useRef, useState } from "react";
import { AiBadges } from "@/components";
import { API_BASE, workerFetch } from "@/lib/api";

type TaskRow = { manual_id: number; job_name: string; task_id: number; task_name: string };
type Step = {
  id: number;
  sort_order: number;
  easy_text: string;
  easier_text: string | null;
  caution_text: string | null;
  photo_path: string | null;
  clip_path: string | null;
  ai_generated: boolean;
  approved_at: string | null;
};
type View = "text" | "easier" | "photo" | "clip" | "called";

const fileUrl = (p: string) => `${API_BASE}/files/${p}`;

function speak(text: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "ko-KR";
  u.rate = 0.9;
  window.speechSynthesis.speak(u);
}

export default function WorkerPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [taskName, setTaskName] = useState("");
  const [steps, setSteps] = useState<Step[]>([]);
  const [idx, setIdx] = useState(0);
  const [view, setView] = useState<View>("text");
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    fetch(`${API_BASE}/w/${token}`)
      .then((r) => {
        if (!r.ok) throw new Error("QR이 맞지 않아요. 담당자에게 알려 주세요.");
        return workerFetch("/w/manuals", token);
      })
      .then(setTasks)
      .catch((e) => setError(String(e.message ?? e)));
  }, [token]);

  const record = useCallback(
    (stepId: number, kind: string) =>
      workerFetch("/w/help", token, { method: "POST", body: JSON.stringify({ step_id: stepId, kind }) }).catch(() => {}),
    [token],
  );

  async function openTask(t: TaskRow) {
    setSteps(await workerFetch(`/w/tasks/${t.task_id}`, token));
    setTaskName(t.task_name);
    setIdx(0);
    setView("text");
  }

  function go(next: number) {
    setIdx(next);
    setView("text");
  }

  if (error) {
    return (
      <main className="worker">
        <p className="big">{error}</p>
      </main>
    );
  }

  // 업무 고르기
  if (steps.length === 0) {
    return (
      <main className="worker">
        <h1 className="title">어떤 일을 할까요?</h1>
        {tasks.length === 0 && <p className="big">아직 준비된 일이 없어요.</p>}
        <div className="stack">
          {tasks.map((t) => (
            <button key={t.task_id} className="choice" onClick={() => openTask(t)}>
              {t.task_name}
            </button>
          ))}
        </div>
      </main>
    );
  }

  const s = steps[idx];
  const shown = view === "easier" && s.easier_text ? s.easier_text : s.easy_text;
  const last = idx === steps.length - 1;

  function press(kind: "repeat" | "easier" | "photo" | "handoff") {
    record(s.id, kind);
    if (kind === "repeat") {
      setView(s.clip_path ? "clip" : "text");
      setTimeout(() => videoRef.current?.play().catch(() => {}), 50);
    } else if (kind === "easier") setView("easier");
    else if (kind === "photo") setView("photo");
    else setView("called");
  }

  return (
    <main className="worker">
      {/* 위: 위치 (고정) */}
      <div className="progress">
        <span>{taskName}</span>
        <span>
          {idx + 1} / {steps.length}
        </span>
      </div>

      {/* 가운데: 한 단계 (고정 영역) */}
      <section className="step">
        {view === "photo" && s.photo_path && <img className="media" src={fileUrl(s.photo_path)} alt="이 단계 사진" />}
        {view === "clip" && s.clip_path && (
          <video ref={videoRef} className="media" src={fileUrl(s.clip_path)} controls playsInline muted />
        )}
        {view === "called" ? (
          <p className="big">담당자를 불렀어요. 잠깐 기다려 주세요.</p>
        ) : (
          <p className="big">{shown}</p>
        )}
        {s.caution_text && view !== "called" && <p className="caution">⚠ {s.caution_text}</p>}
        <button className="listen" onClick={() => speak([shown, s.caution_text].filter(Boolean).join(". "))}>
          🔊 소리로 듣기
        </button>
        <AiBadges aiGenerated={s.ai_generated} approvedAt={s.approved_at} />
      </section>

      {/* 아래: 도움 단추 (고정) */}
      <div className="help-grid">
        <button onClick={() => press("repeat")}>다시 보여줘</button>
        <button onClick={() => press("easier")} disabled={!s.easier_text}>
          더 쉽게
        </button>
        <button onClick={() => press("photo")} disabled={!s.photo_path}>
          사진으로
        </button>
        <button className="call" onClick={() => press("handoff")}>
          사람 불러줘
        </button>
      </div>

      <div className="nav">
        <button onClick={() => go(Math.max(0, idx - 1))} disabled={idx === 0}>
          ← 이전
        </button>
        {last ? (
          <button
            className="primary"
            onClick={() => {
              record(s.id, "done");
              setSteps([]);
            }}
          >
            다 했어요
          </button>
        ) : (
          <button className="primary" onClick={() => go(idx + 1)}>
            다음 →
          </button>
        )}
      </div>
    </main>
  );
}
