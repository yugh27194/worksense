import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 개발 모드 표시(왼쪽 아래 'N')가 근로자 화면의 「이전」 단추를 가려 시연에 방해된다
  devIndicators: false,
};

export default nextConfig;
