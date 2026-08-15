# webapp Bootstrap 전환 — 작업 로그

## 2026-08-11 | 시작

사용자가 "webapp이 너무 안이쁜데, 적용 가능한 Theme가 있을까?"로 시작 → 커스텀 CSS
분량(templates 908줄 + style.css 486줄)을 보고 classless 프레임워크(Pico.css 등)는
이미 커스텀 클래스 위주라 효과가 제한적이라고 판단, Bootstrap 전면 전환을 제안함.
사용자가 "Bootstrap과 같은 프레임워크로 갈아타고 싶은데 작업량이 얼마나 될까?"로
확인 요청 → 항목별 작업량(레이아웃/카드·표/폼/다크모드/반응형/QA) 브리핑 후 두 가지
결정 확인.

**결정: 기본 Bootstrap 색상 + OS 자동 다크모드 감지 유지** (사용자가 두 질문 모두
추천 옵션 선택).

**Why:** Bootswatch 같은 완성 테마는 예뻐 보이지만 색상 변수 재조정이 추가로 필요하고,
수동 다크모드 토글은 지금 없던 UI를 새로 추가하는 것이라 범위가 커짐 — 사용자가 둘 다
"지금 있는 동작 유지 + 최소 변경" 쪽을 선택함.

**How to apply:** Bootstrap 기본 팔레트 그대로 쓰고, `--bs-primary` 등 색상 변수 오버라이드
안 함. 다크모드는 `prefers-color-scheme` 감지 인라인 스크립트로 `data-bs-theme` 설정,
토글 버튼 없음.

## 2026-08-11 | 구현 및 검증 완료

**레이아웃 재설계 핵심 결정: 사이드바를 Bootstrap `offcanvas-lg`로 교체.** 기존
커스텀 `.shell`/`.sidebar` + 수동 햄버거 토글/백드롭 JS가 하던 일(데스크톱은 고정
사이드바, 모바일은 드로어)을 Bootstrap 5.2+의 반응형 오프캔버스 컴포넌트가 그대로
대체해줌 — 커스텀 JS(토글/백드롭 클릭 리스너)를 통째로 삭제하고 `data-bs-toggle`
속성만으로 동일 동작(ARIA/ESC 닫기 포함, 기존엔 없던 접근성 개선까지 덤으로)을 얻음.

**카테고리 그룹(`<details>`) → Bootstrap `accordion`**, 속성/값 목록(`row-list`) →
`<dl class="row">` (Bootstrap 문서에 나온 정의형 리스트 패턴 그대로 재사용, 별도
CSS 없이 라벨-값 정렬이 됨).

**`static/style.css` 486줄 → 15줄로 축소**: 라이트/다크 CSS 변수(`--fg`/`--bg`/
`--border` 등) 전부 삭제 — Bootstrap이 `data-bs-theme`로 자체 변수 체계를 가지고
있어서 중복이었음. 남긴 건 Bootstrap 컴포넌트로 표현 안 되는 3개뿐: `.hover-bg`
(리스트 밖 링크의 hover 배경), `.value-text`(원본 텍스트 줄바꿈 보존을 위한
`white-space: pre-wrap`), `.chat-frame`(iframe이 `main`의 패딩을 상쇄하고 꽉 차게).

**검증**: Flask test_client로 70개 카테고리 전체 목록 페이지 + 카테고리별
속성+표 개수가 가장 많은(렌더링 복잡도 최고) 항목 상세 페이지 총 140건 전부 200
확인. 로컬 컨테이너 재빌드 후 Playwright로 라이트/다크 × 데스크톱/모바일 5개
페이지 타입 스크린샷 + 모바일 offcanvas 드로어 실제 오픈 확인 + 폼 페이지 속성/표
동적 행 추가·삭제 JS 정상 동작 확인. NAS(`./deploy.sh webapp`)까지 배포 완료,
배포 후 응답에서 Bootstrap CDN/offcanvas-lg 마크업 존재 + 이전 커스텀
`class="shell"` 마크업 소멸을 확인해 실제 반영을 검증함.

**미해결:** 사이드바 accordion 버튼의 긴 한글 라벨(예: "그레이드보너스",
"선박기본재질")이 240px 고정폭에서 2~3줄로 줄바꿈됨 — 글자가 잘리거나 음절이
쪼개지진 않아 기능상 문제는 없지만 다소 빽빽해 보임. 사용자가 지적하면 사이드바
폭을 늘리거나 폰트 크기를 줄이는 정도로 후속 조정 가능.

## 2026-08-14 | 버그 수정 — 사이드바 세로 스크롤 안 됨

사용자 리포트: 카테고리 그룹(대분류)을 펼쳤을 때 목록이 길어지면 화면 아래로 잘려서
안 보이는데 스크롤바가 없음.

**원인 조사**: 처음엔 "Bootstrap이 `.offcanvas-lg`에 `height:auto!important`를 강제한다"고
(기억에 의존해) 잘못 추정하고 그에 맞춰 1차 수정했으나 재현 테스트에서 효과 없음 확인.
실제 배포된 Bootstrap 5.3.3 CSS를 직접 받아 `.offcanvas-lg` 관련 규칙을 전부 확인한 결과,
진짜 원인은 lg 이상(992px+)에서 `.offcanvas-lg .offcanvas-body`에 `overflow-y: visible`이
적용되고 높이도 안 채워진다는 것 — 그래서 긴 콘텐츠가 사이드바 밖으로 그냥 흘러넘치고,
부모(`.shell-row`)의 `overflow-hidden`에 스크롤 없이 잘려나감.

**수정**: `templates/base.html`의 사이드바 바깥 flex 컨테이너에 `.shell-row` 클래스 추가.
`static/style.css`에 `.shell-row { min-height: 0 }`(flex item 기본 min-height:auto가
콘텐츠 크기만큼 부모를 vh-100 밖으로 늘리는 것 방지) + `@media (min-width: 992px)`
안에서 `#sidebar.offcanvas-lg { height: 100% !important }` / `.offcanvas-body { height:
100%; overflow-y: auto !important }`로 Bootstrap 기본값을 오버라이드.

**검증**: 로컬에서 NAS PostgreSQL에 직접 붙여 Flask 개발서버로 실행(포트 5051 — 5050은
이미 다른 프로세스가 점유 중이어서, 실수로 남의 프로세스 안 건드리게 새 포트 사용).
Playwright 스크립트로 `#nav-accordion`의 `scrollHeight`(931) > `clientHeight`(538),
`overflow-y: auto` 확인 + 실제 스크롤 후 스크린샷으로 아래쪽 그룹(선박/인물·스킬/NPC/세계)과
`chat.ai` 버튼까지 다 보이는 것 확인. 회귀 확인: 홈 화면(그룹 전부 접힘, 짧은 상태) 정상,
모바일 뷰포트(992px 미만)에서 오프캔버스 드로어 열기 정상 — `min-width:992px` 스코프라
모바일 동작엔 영향 없음.

**미해결**: NAS 배포는 아직 안 함 — 사용자 확인 후 진행.
