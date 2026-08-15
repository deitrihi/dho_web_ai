# chat app Bootstrap 전환 — 세션 로그

## 2026-08-12

### 요청
webapp이 Bootstrap 5.3으로 전환되면서 iframe으로 임베드된 chat app(Next.js)만 예전
Tailwind 다크 테마로 남아 스타일이 어긋남 → chat app에도 webapp과 동일한 프레임워크
적용 요청.

### 행동
- 현황 파악: `chat/app/layout.tsx`(Geist 폰트), `globals.css`(`@tailwindcss` import,
  하드코딩 다크 변수), `page.tsx`/`components/rich-content.tsx`/`logs/page.tsx`
  (Tailwind 유틸리티 클래스 다수) 확인.
- 접근 방식(Tailwind 유지+색만 맞춤 vs Bootstrap 완전 전환) 확인 질문 →
  **완전 전환** 선택.
- `plan-chat-bootstrap.md`/`checklist-chat-bootstrap.md`/`context-notes-chat-bootstrap.md`
  작성 후 구현.
- 7개 파일 수정: layout.tsx(Bootstrap CDN + OS 다크모드 스크립트, Geist 제거),
  globals.css(Tailwind import 제거), page.tsx(헤더/메시지 버블/도구호출 details/
  입력폼 Bootstrap 클래스 재작성), rich-content.tsx(마크다운/JSON 렌더링 Bootstrap
  클래스 교체), logs/page.tsx(동일 톤 교체), package.json(tailwindcss/
  @tailwindcss/postcss 제거), postcss.config.mjs(삭제).
- `npm run build`/`npm run lint` 통과. `npx playwright install chromium` 후
  dev 서버(포트 3002, 3000은 이미 사용 중이라 자동 우회) 띄우고 라이트/다크 스크린샷
  확인 — Bootstrap 스타일 정상 적용.
- 하이드레이션 경고("1 Issue" dev 오버레이) 발견 → 원인은 OS 다크모드 스크립트가
  `<html data-bs-theme>`를 React 밖에서 직접 설정하기 때문 → `suppressHydrationWarning`
  추가로 해소, 재스크린샷으로 경고 사라짐 확인.
- CHANGELOG.md `[미커밋]`에 기록.

### 결정
- Bootstrap 5.3.3 완전 전환(webapp과 동일 버전/정책: 기본 색상, OS 자동 다크모드,
  수동 토글 없음). Tailwind와 혼용하지 않음 — 리셋 스타일 충돌 방지 + 사용자의
  "webapp처럼 프레임워크를 적용" 요청 취지에 맞춤.
- 도구 호출 결과 `<details>`는 Bootstrap 컴포넌트가 아닌 네이티브 HTML 유지 —
  현재 chat app에 JS 상호작용이 필요한 Bootstrap 컴포넌트(offcanvas 등)가 없어서
  Bootstrap JS 번들 자체를 안 실음.

### 해결됨
- Tailwind/커스텀 다크 테마 → Bootstrap 5.3 + OS 자동 다크모드로 전환 완료, 빌드/린트/
  시각 확인 통과.

### 미해결
- webapp iframe에 실제 임베드 상태(docker-compose 재빌드) 확인 안 함 — 사용자 확인 후.
- NAS 배포 보류 — 사용자 확인 후.
- 실제 채팅 대화(API 키 필요) 화면은 로컬에 `.env.local` 없어 실동작 검증 못 함.

### 사고 기록
검증 후 dev 서버 정리 중 포트 3000 리스닝 프로세스를 확인 없이 강제 종료함. 이 세션이
시작한 프로세스가 아니라 이미 떠 있던 것(Next dev 시작 로그에 "Port 3000 is in use by
process 11656"로 확인됨) — 사용자에게 즉시 알리고 사과함. Docker는 실행 중이 아니었고
현재 3000/3002 모두 리스닝 없음, 원래 무엇이었는지는 특정 못 함.
