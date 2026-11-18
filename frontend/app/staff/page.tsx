"use client";

// 담당자 웹 (인계서 8장): 1 자료 업로드 → 2 분석 진행 → 3 매뉴얼 검토 → 4 승인 → 5 개선 요청 → 6 QR·현장 용어
// 지금은 1·2·6 의 최소 동작만 있다. 3~5 는 백엔드 TODO 와 Figma 시안 확정 후 채운다.
import { useState } from "react";
import { staffFetch } from "@/lib/api";

type Stage = { stage: string; status: string; error: string | null };

export default function StaffPage() {
  const [workplaceId, setWorkplaceId] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [consent, setConsent] = useState(false);
  const [mediaId, setMediaId] = useState<number | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [qr, setQr] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload() {
    if (!file) return;
    setError(null);
    const fd = new FormData();
    fd.append("kind", "workplace_video");
    fd.append("title", title);
    fd.append("consent_confirmed", String(consent));
    fd.append("file", file);
    try {
      const { id } = await staffFetch("/media", workplaceId, { method: "POST", body: fd });
      setMediaId(id);
      await staffFetch(`/media/${id}/analyze`, workplaceId, { method: "POST" });
      await refresh(id);
    } catch (e) {
      setError(String(e));
    }
  }

  async function refresh(id = mediaId) {
    if (id == null) return;
    const res = await staffFetch(`/jobs/${id}`, workplaceId);
    setStages(res.stages);
  }

  async function issueQr() {
    const res = await staffFetch(`/workplaces/${workplaceId}/qr`, workplaceId, { method: "POST" });
    setQr(res.path);
  }

  return (
    <main>
      <h1>담당자 화면</h1>
      <label>
        사업장 ID (개발용)
        <input type="number" value={workplaceId} onChange={(e) => setWorkplaceId(Number(e.target.value))} />
      </label>

      <section className="card">
        <h2>1. 자료 업로드</h2>
        <label>
          제목
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="예: 오픈 준비" />
        </label>
        <label>
          업무교육 영상
          <input type="file" accept="video/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <label>
          <input type="checkbox" style={{ width: "auto" }} checked={consent} onChange={(e) => setConsent(e.target.checked)} />{" "}
          촬영 허가와 이용 동의를 받은 자료입니다
        </label>
        <button onClick={upload} disabled={!file || !consent}>
          업로드하고 분석 시작
        </button>
        {error && <p className="warn">{error}</p>}
      </section>

      {mediaId != null && (
        <section className="card">
          <h2>2. 분석 진행</h2>
          <ol>
            {stages.map((s, i) => (
              <li key={i}>
                {s.stage} — {s.status} {s.error && <span className="warn">({s.error})</span>}
              </li>
            ))}
          </ol>
          <button onClick={() => refresh()}>새로고침</button>
        </section>
      )}

      <section className="card">
        <h2>6. 근로자 QR 발급</h2>
        <button onClick={issueQr}>QR 링크 만들기</button>
        {qr && (
          <p>
            접속 경로: <a href={qr}>{qr}</a>
          </p>
        )}
      </section>
    </main>
  );
}
