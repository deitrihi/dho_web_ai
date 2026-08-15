# chat app Bootstrap 전환 체크리스트

- [x] `chat/app/layout.tsx` — Bootstrap 5.3 CDN 추가, 다크모드 자동 감지 스크립트, Geist 폰트 제거
- [x] `chat/app/globals.css` — Tailwind import 제거, 최소 커스텀만 유지
- [x] `chat/app/page.tsx` — 헤더/메시지 버블/도구호출/입력폼 Bootstrap 클래스로 재작성
- [x] `chat/app/components/rich-content.tsx` — 마크다운/JSON 렌더링 Bootstrap 클래스로 교체
- [x] `chat/app/logs/page.tsx` — 에러 로그 페이지 Bootstrap 클래스로 교체
- [x] `chat/package.json` — tailwindcss, @tailwindcss/postcss 제거
- [x] `chat/postcss.config.mjs` — 삭제
- [x] `npm run build` (chat/) 로 빌드 확인
- [x] `npm run lint` (chat/) 확인
- [x] 로컬 dev 서버 + Playwright 스크린샷으로 라이트/다크 시각 확인 (홈/로그 페이지)
- [x] NAS에 배포된 chat 컨테이너 자체 확인 (`/chat` 200 응답 + Bootstrap CDN 로드 확인)
- [ ] webapp 안 iframe으로 실제 임베드된 화면 확인 (리버스 프록시 통한 실 도메인 접속 필요 — 사용자가 브라우저로 직접 확인)
- [x] CHANGELOG.md `[미커밋]`에 기록
- [x] 세션 로그 기록 (`claude_logs/`, 옵시디언)
- [x] NAS 배포 (`./deploy.sh chat`)
