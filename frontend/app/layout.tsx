import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "일머RE",
  description: "누구나 자신의 속도로 배우는 AI OJT",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
