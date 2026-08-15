# chat app Bootstrap 전환

## 배경
webapp이 Bootstrap 5.3으로 전환([[plan-bootstrap-migration]])되면서, iframe으로 webapp에
임베드되는 chat app(Next.js)만 예전 스타일(Tailwind, 하드코딩된 다크 테마)로 남아 시각적으로
어긋남. webapp과 동일한 프레임워크/테마 정책을 chat app에도 적용한다.

## 결정 사항 (사용자 확인)
- **Tailwind 완전 제거, Bootstrap 5.3 CDN으로 전환** (webapp과 동일 버전).
- 색상/다크모드 정책도 webapp과 동일하게: 기본 Bootstrap 색상, OS 설정
  (prefers-color-scheme) 자동 감지, 수동 토글 없음.

## 대상 파일
- `chat/app/layout.tsx` — Bootstrap CDN link/script 추가, Geist 폰트 제거, OS 다크모드
  감지 인라인 스크립트(base.html과 동일 로직) 추가.
- `chat/app/globals.css` — `@import "tailwindcss"` 및 커스텀 다크 변수 제거. Bootstrap이
  커버 못 하는 최소 오버라이드만 남김(webapp의 style.css 축소 패턴과 동일).
- `chat/app/page.tsx` — 메인 챗 UI(헤더/메시지 버블/도구호출 details/입력폼)의 Tailwind
  className을 Bootstrap 컴포넌트(card, list-group, badge, form-control, btn, accordion 등)로
  재작성.
- `chat/app/components/rich-content.tsx` — 마크다운 렌더링(MarkdownText)과 JSON 렌더링
  (JsonValue/JsonTable)의 Tailwind 클래스를 Bootstrap 표/텍스트 유틸리티로 교체.
- `chat/app/logs/page.tsx` — 에러 로그 페이지도 동일 톤으로 교체.
- `chat/package.json` — `tailwindcss`, `@tailwindcss/postcss` devDependency 제거.
- `chat/postcss.config.mjs` — Tailwind 전용 설정이므로 파일 삭제.

## 범위 밖
- webapp 쪽 파일(`templates/*`, `static/style.css`)은 이미 완료된 별도 작업이라 건드리지 않음.
- 채팅 로직(route.ts, dho-db.ts)은 스타일 작업과 무관하므로 변경하지 않음.
- Bootswatch 등 완성 테마 적용 안 함, 수동 다크모드 토글 버튼 추가 안 함(webapp과 동일 범위 제한).
