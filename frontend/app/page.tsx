import Link from "next/link";

export default function Home() {
  return (
    <main>
      <h1>일머RE</h1>
      <p>업무교육 영상을 쉬운 단계별 매뉴얼로 바꾸고, 일하는 중에 질문할 수 있는 AI OJT 서비스입니다.</p>
      <ul>
        <li><Link href="/staff">담당자 화면</Link></li>
        <li>근로자 화면은 담당자가 발급한 QR(<code>/w/&lt;토큰&gt;</code>)로 들어옵니다.</li>
      </ul>
    </main>
  );
}
