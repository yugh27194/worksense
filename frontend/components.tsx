// AI 생성물 표시 (인계서 1.4 #7, 8장): 'AI가 만든 내용'과 '담당자 확인 완료'를 항상 붙인다.
export function AiBadges({ aiGenerated, approvedAt }: { aiGenerated: boolean; approvedAt?: string | null }) {
  return (
    <div>
      {aiGenerated && <span className="badge">AI가 만든 내용</span>}
      {approvedAt && <span className="badge">담당자 확인 완료</span>}
    </div>
  );
}
