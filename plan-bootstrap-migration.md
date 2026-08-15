# webapp Bootstrap 전환

## 배경
사용자 피드백: "webapp이 너무 안이쁜데" → Bootstrap 같은 프레임워크로 갈아타고 싶음.
현재 `dho_webapp.py` + `templates/*.html`(7개, 908줄) + `static/style.css`(486줄)는
전부 커스텀 CSS(라이트/다크 변수, 사이드바, 카드, 표, 뱃지, 폼)로 손수 작성돼 있음.

## 결정 사항 (사용자 확인)
- 색상 테마: **기본 Bootstrap 색상** 그대로 사용 (accent 색상 유지/Bootswatch 안 씀).
- 다크모드: **OS 설정(prefers-color-scheme) 자동 감지 유지**, 수동 토글 버튼 없음.

## 접근 방식
- 빌드 도구(webpack/npm) 도입 없이 Bootstrap 5.3 CDN `<link>`/`<script>` 한 줄로 추가.
  Flask+Jinja 구조는 그대로 유지.
- 레이아웃(`base.html`): 커스텀 `.shell`/`.sidebar`/`.main-col` + 수동 모바일 드로어 JS를
  Bootstrap `navbar` + `offcanvas-lg`(5.2+ 반응형 오프캔버스 — lg 이상에서는 고정
  사이드바, 그 아래에서는 자동으로 드로어가 됨)로 교체. 커스텀 백드롭/토글 JS 삭제하고
  Bootstrap offcanvas 내장 동작(백드롭/ARIA/ESC 닫기)으로 대체.
- 사이드바 카테고리 그룹(`<details>`)은 Bootstrap `accordion` 컴포넌트로 교체.
- 카드/뱃지/표(`item.html`/`category.html`/`search.html`/`index.html`)는 Bootstrap
  `card`/`badge`/`table` 클래스로 거의 1:1 교체. 정렬 가능한 pivot 테이블 헤더 링크,
  backlink 그룹핑 로직 등 서버 사이드 로직은 그대로 유지, 클래스만 교체.
- 폼(`item_form.html`): 속성/표 행 동적 추가·삭제하는 vanilla JS(`<template>` 클론)는
  그대로 유지, 커스텀 CSS 그리드(`form-row`/`form-table-block`)를 Bootstrap
  `row`/`col-*` 체계로 교체.
- 다크모드: Bootstrap 5.3은 `data-bs-theme` 속성 기반이라 OS 설정을 따라가려면 작은
  인라인 스크립트가 필요함 — `<head>`에서 `prefers-color-scheme` 확인 후 즉시
  `data-bs-theme` 설정(깜빡임 방지) + `matchMedia` change 리스너로 실시간 반영
  (기존 CSS-only 방식과 동일하게 OS 설정 변경 시 새로고침 없이 반영).
- `static/style.css`는 Bootstrap이 커버 못 하는 최소한만 남긴다: 표 hover/sort
  화살표, backlink 배지 레이아웃 등 Bootstrap에 없는 세부 요소. 나머지(사이드바/카드/
  버튼/폼 기본 스타일)는 전부 삭제.

## 범위 밖
- Bootswatch 등 완성 테마 적용 안 함(사용자가 기본 색상 선택).
- 수동 다크모드 토글 버튼 추가 안 함(사용자가 OS 자동 감지 유지 선택).
- 이미지 렌더링/링크 치환(`render_text_with_links`) 등 서버 사이드 로직은 안 건드림.
