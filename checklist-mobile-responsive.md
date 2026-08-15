# 모바일 반응형 체크리스트

## webapp (Flask)
- [x] `templates/base.html`에 `<meta name="viewport" content="width=device-width, initial-scale=1">` 추가
- [x] 모바일(≤768px) 햄버거 버튼 + 드로어 사이드바(오버레이/백드롭) 추가 — 토글 JS 포함
- [x] `static/style.css`: `.row`/`.row-label` 좁은 화면에서 세로 스택으로 전환
- [x] `static/style.css`: `.form-row`/`.form-table-block` 좁은 화면에서 단일 컬럼으로 전환
- [x] `static/style.css`: breadcrumb/topbar 좁은 화면 패딩·폰트 축소, breadcrumb 넘칠 때
      가로 스크롤 허용(잘림 대신)
- [x] `static/style.css`: 사이드바/폼 버튼 등 터치 타겟 크기(≤768px에서 최소 높이) 보정
- [x] `category-grid`/`backlink-list` grid의 `minmax` 값이 360px 폭에서도 안 깨지는지 확인
- [x] (추가 발견) `.shell`의 `height: 100vh`가 모바일 주소창 유무에 따라 화면보다 커져
      `overflow:hidden`과 만나 콘텐츠가 잘리는 문제 — `height: 100dvh` 폴백 추가

## chat (Next.js)
- [x] `app/page.tsx`: `min-h-screen` → `min-h-dvh`(모바일 주소창/키보드 대응)
- [x] `app/page.tsx`: 도구 호출 `<summary>` 텍스트에 `break-all` 추가해 가로 스크롤 방지
- [x] (추가 발견) 메시지 버블에 `break-words` 추가 — 공백 없는 긴 텍스트(URL 등)로 인한
      가로 스크롤 방지
- [ ] 좁은 화면(360~430px) 실제 브라우저 육안 확인은 미완 (아래 검증 항목 참고)

## 검증
- [x] webapp: Flask test_client로 `/`, `/cannon`, `/cannon/<id>`, `/cannon/new`,
      `/cannon/<id>/edit`, `/assistant` 200 확인 + viewport meta/nav-toggle 마크업 존재 확인
- [x] chat: `npm run build`, `npm run lint` 통과
- [ ] 실제 브라우저 DevTools 모바일 에뮬레이션 육안 확인은 미완 (다음 세션 또는 사용자 확인 필요)
