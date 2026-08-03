// Docker 배포용 설정 (NAS docker-compose에서 사용)
import type { NextConfig } from "next";

// nginx가 이 앱을 /chat 같은 서브패스로 프록시할 때 씀 (빌드 타임에만 반영됨, 안 바꾸면 빈 값 —
// 로컬 `npm run dev`는 그대로 루트에서 동작). docker-compose.yml의 build.args에서 넘어옴.
const basePath = process.env.NEXT_BASE_PATH || "";

const nextConfig: NextConfig = {
  output: "standalone",
  basePath,
  env: {
    // 클라이언트 코드(app/page.tsx)에서 API 경로를 조립할 때 같은 값을 쓰기 위해 노출
    NEXT_PUBLIC_BASE_PATH: basePath,
  },
};

export default nextConfig;
