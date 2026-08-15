# webapp Bootstrap 전환

## 요청
- "webapp이 너무 안이쁜데, 적용 가능한 Theme가 있을까?" → 작업량 문의 → "진행해줘"
  → "nas에 배포 해줘".

## 행동
- 커스텀 CSS(486줄) + 템플릿 7개(908줄)를 Bootstrap 5.3(CDN) 기반으로 전면 재작성.
  - `base.html`: navbar + `offcanvas-lg` 반응형 사이드바(데스크톱 고정/모바일 드로어,
    Bootstrap 내장 동작으로 커스텀 토글/백드롭 JS 삭제), 카테고리 그룹은 accordion,
    다크모드는 `prefers-color-scheme` 인라인 스크립트로 `data-bs-theme` 자동 설정.
  - `index.html`/`category.html`/`item.html`/`search.html`/`item_form.html`: 카드/
    뱃지/표/폼을 Bootstrap 컴포넌트로 교체, 속성 목록은 `<dl class="row">`, 정렬
    가능한 표 헤더 링크와 폼의 동적 행 추가·삭제 JS 등 서버/클라이언트 로직은 유지.
  - `static/style.css`: 486줄 → 15줄(Bootstrap이 못 담당하는 hover-bg/value-text/
    chat-frame 3개만 남김, 라이트/다크 커스텀 변수 전부 삭제).
- 검증: Flask test_client로 70개 카테고리 전체 + 카테고리별 최다 복잡도 항목
  140건 200 확인, 로컬 컨테이너 재빌드 후 Playwright로 라이트/다크 × 데스크톱/
  모바일 스크린샷 + offcanvas 드로어 오픈 + 폼 동적 행 JS 동작 확인.
- `./deploy.sh webapp`로 NAS 배포, 배포 후 응답에 Bootstrap CDN/offcanvas 마크업
  존재 확인으로 실제 반영 검증.
- `CHANGELOG.md` 기록.

## 결정
- 색상: 기본 Bootstrap 팔레트 그대로(Bootswatch 등 완성 테마 안 씀).
- 다크모드: 기존과 동일하게 OS 자동 감지 유지, 수동 토글 버튼 없음.
- 두 결정 모두 사용자가 작업량 브리핑 후 추천 옵션 선택.

## 해결된 문제
- 없음(신규 리스킨, 기능 회귀 없음).

## 미해결
- 사이드바 accordion의 긴 카테고리 라벨이 240px 폭에서 2~3줄로 줄바꿈됨(기능 문제는
  아님, 사용자가 원하면 폭/폰트 크기 후속 조정 가능).

## 2026-08-14 | 버그 수정 — 사이드바 스크롤 안 됨

### 요청
"webapp 좌측 카테고리가 트리 구조라 세로로 길어지는 경우가 있는데, 스크롤바가 없어서
아래 내용을 볼 수 없다."

### 행동
- NAS의 실제 webapp(`/equipment`, 뷰포트 1280x650)을 Playwright로 스크린샷해서 재현
  확인 — "아이템" 그룹을 펼쳤을 때 목록이 뷰포트 아래로 잘리고 스크롤바 없음.
- 1차 시도: "Bootstrap이 `.offcanvas-lg`에 height:auto!important를 강제한다"는 기억에
  의존한 추정으로 수정했으나 재현 테스트에서 효과 없음.
- Bootstrap 5.3.3 CSS를 직접 받아 확인한 결과 진짜 원인 특정: lg 이상(992px+)에서
  `.offcanvas-lg .offcanvas-body`에 `overflow-y: visible`이 적용되고 높이도 안 채워짐 —
  긴 콘텐츠가 그냥 흘러넘쳐서 부모(`.shell-row`)의 `overflow-hidden`에 스크롤 없이 잘림.
- `templates/base.html`에 `.shell-row` 클래스 추가, `static/style.css`에 `min-height:0`
  (flex item 기본값이 vh-100 밖으로 부모를 늘리는 것 방지) + `@media (min-width:992px)`
  안에서 `#sidebar.offcanvas-lg`/`.offcanvas-body`에 `height:100%` + `overflow-y:auto
  !important` 오버라이드 추가.
- 로컬 검증: NAS PostgreSQL에 직접 연결해 Flask 개발서버를 새 포트(5051)에서 실행(포트
  5050은 이미 다른 프로세스가 점유 중이어서 새 포트 사용 — 지난 세션에 포트 3000
  실수가 있어서 이번엔 프로세스를 건드리기 전에 명령줄까지 확인). Playwright 스크립트로
  `#nav-accordion`이 실제 스크롤 컨테이너가 됨(scrollHeight 931 > clientHeight 538,
  overflow-y:auto) 확인, 스크롤 후 스크린샷으로 하단 그룹/chat.ai 버튼까지 보이는 것
  확인. 회귀 확인: 홈 화면(짧은 상태)·모바일 오프캔버스 드로어 모두 정상.
- CHANGELOG.md 기록.

### 결정
- 없음(순수 버그 수정, 디자인 변경 없음).

### 해결된 문제
- 사이드바 카테고리 그룹이 길어질 때 스크롤 안 되던 문제 해결.

### 미해결
- NAS 배포는 사용자 확인 후 진행.
