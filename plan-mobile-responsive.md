# 모바일 반응형 대응

## 목표
`webapp`(Flask, `templates/`+`static/style.css`)과 `chat`(Next.js, `chat/app/`) 둘 다
일반적인 모바일 해상도(360~430px 폭 기준)에서 정상적으로 쓸 수 있게 만든다. 데스크톱
레이아웃/디자인은 그대로 유지하고, 좁은 화면에서만 다르게 동작하도록 반응형으로 확장한다.

## 진단
- **webapp**: `templates/base.html`에 `<meta name="viewport">` 태그 자체가 없음. 이게 있어야
  모바일 브라우저가 실제 화면 폭 기준으로 레이아웃하고 기존 `@media (max-width: 768px)` 규칙이
  의미를 가짐 — 지금은 데스크톱 폭(약 980px)으로 그려놓고 축소시켜 보여주는 상태라 사실상
  반응형 규칙이 전혀 작동하지 않음. 이게 "전혀 대응 못함"의 근본 원인.
- 위 규칙이 작동하게 고쳐도, 768px 이하에서 `.sidebar { display:none }`만 있고 대체
  내비게이션(햄버거 메뉴 등)이 없어서 카테고리 이동 자체가 불가능해짐 — 별도 드로어 메뉴 필요.
- 속성 목록(`.row`)이 라벨 120px 고정 폭 + 값 flex라서 좁은 화면에서 값 영역이 지나치게
  좁아짐 — 좁은 화면에서는 라벨을 값 위로 쌓는 형태로 전환 필요.
- 항목 생성/수정 폼(`.form-row`, `.form-table-block`)도 `160px 1fr 28px` 고정 그리드라 좁은
  화면에서 입력칸이 눌림 — 단일 컬럼으로 전환 필요.
- 표는 이미 `.table-scroll { overflow-x:auto }`로 감싸져 있어 가로 스크롤 자체는 됨(유지).
- **chat**: Next.js App Router라 viewport meta는 기본 자동 삽입됨(확인: `node_modules/next/dist/docs`).
  Tailwind 반응형 클래스도 이미 어느 정도 있어 완전히 깨지진 않지만,
  1) `min-h-screen`(=100vh)이 모바일 브라우저 주소창/키보드에 따라 실제 화면보다 크게 잡혀
     하단 입력창이 화면 밖으로 밀리는 문제가 생길 수 있음 → `min-h-dvh`로 교체.
  2) 도구 호출 `<summary>` 줄의 `JSON.stringify(input)`이 공백 없는 긴 문자열이라 좁은
     화면에서 줄바꿈이 안 되고 가로 스크롤을 유발함 → `break-all` 필요.
  webapp의 `/assistant` 라우트가 chat을 iframe으로 감싸는데, iframe 자체 크기는 부모(webapp)
  레이아웃이 결정하므로 webapp viewport 수정이 이 경로에도 필요.

## 접근 방식
1. webapp: viewport meta 추가(근본 원인) → 모바일 드로어 내비게이션 추가 → 나머지 좁은 화면
   레이아웃(속성 리스트, 폼, 타이포/터치 타겟) 순차 보정.
2. chat: `min-h-dvh` 등 모바일 뷰포트 단위 교체 + 도구 호출 텍스트 줄바꿈 수정 + 좁은 화면
   여백/터치 타겟 점검.
3. 데스크톱 레이아웃은 기존 그대로 유지 — 전부 `@media (max-width: ...)` 안에서만 변경하거나
   Tailwind 반응형 프리픽스(`sm:`)로 좁은 화면 전용 스타일만 추가.

## 검증
- webapp: Flask 개발 서버 기동 후 브라우저 DevTools 모바일 에뮬레이션(iPhone SE 375px,
  일반 안드로이드 360~412px)으로 홈/카테고리 목록/상세/폼/챗봇 임베드 페이지 확인.
- chat: `npm run dev`로 기동 후 같은 에뮬레이션으로 확인, `npm run build`/`npm run lint` 통과.
