# webapp Bootstrap 전환 체크리스트

- [x] `templates/base.html` — Bootstrap 5.3 CDN 추가, navbar + offcanvas-lg 사이드바,
      accordion 카테고리 그룹, 다크모드 자동 감지 스크립트
- [x] `templates/index.html` — 카테고리 그룹 카드
- [x] `templates/category.html` — 정렬 가능한 목록 표
- [x] `templates/item.html` — 상세 카드, 속성/표 렌더링, backlink 섹션
- [x] `templates/search.html` — 검색 결과 카드/배지
- [x] `templates/item_form.html` — 폼 그리드 (동적 행 추가/삭제 JS 유지)
- [x] `templates/chat.html` — iframe 래퍼(변경 없음, .chat-frame 클래스만 유지)
- [x] `static/style.css` — Bootstrap이 커버 못 하는 최소 오버라이드만 남기고 정리
      (486줄 → 15줄: hover-bg/value-text/chat-frame 3개만 남김)
- [x] 로컬 컨테이너로 시각 확인 (라이트/다크 × 데스크톱/모바일, 5개 페이지 타입 +
      모바일 offcanvas 드로어 오픈 확인)
- [x] 폼 페이지 실동작 확인 (Playwright로 속성/표 행 추가·삭제 JS 동작 확인)
- [x] Flask test_client 스모크 테스트 — 70개 카테고리 전체 목록 페이지 +
      카테고리별 가장 복잡한(속성+표 개수 최다) 항목 상세 페이지, 총 140건 전부
      200 확인
- [x] CHANGELOG.md `[미커밋]`에 기록
- [x] 세션 로그 기록 (`claude_logs/`, 옵시디언)
- [x] NAS 배포 (사용자 확인 후, `./deploy.sh webapp`)
- [x] 사이드바 세로 스크롤 버그 수정 및 재배포 (2026-08-14, `./deploy.sh webapp`)
