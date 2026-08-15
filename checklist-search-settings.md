# 검색 결과 대분류 순서 설정 페이지 체크리스트

- [x] `dho_webapp.py`: `search_group_order` 테이블 `CREATE TABLE IF NOT EXISTS`(모듈
      로드 시), `get_search_group_order()` 헬퍼(커스텀 값 없으면 category_localization
      기본 순서로 폴백)
- [x] `/settings` GET 라우트 — 현재 대분류 순서 표시
- [x] `/settings/move-group` POST 라우트 — 그룹 위/아래 이동, 저장 후 리다이렉트
- [x] `get_search_results()` — 그룹 순서(설정값) → 그룹 내 매칭 건수 내림차순으로 정렬
- [x] `templates/settings.html` 신규
- [x] `templates/base.html` 상단바에 "설정" 링크 추가
- [x] 로컬 스모크 테스트: 기본 상태(설정 없음) 검색 결과 순서 확인 → "세계" 그룹을
      맨 위로 이동 → 검색 결과에서 세계 그룹 카테고리가 실제로 맨 앞으로 이동하는 것
      확인. 145개 라우트 전체 스모크 테스트 통과. Playwright로 설정 페이지
      ▲/▼ 버튼 클릭 → 순서 변경 반영 시각 확인
- [x] CHANGELOG.md `[미커밋]`에 기록
- [x] 세션 로그 기록
- [x] NAS 배포 (사용자 확인 후)

## 추가 — 대분류 하위 소분류 순서
- [x] `search_category_order` 테이블(`CREATE TABLE IF NOT EXISTS`), `get_effective_category_order()`/
      `get_customized_search_groups()` 헬퍼
- [x] `/settings/move-category` POST 라우트, `settings()`가 대분류별 소분류 목록(라벨
      포함)까지 담아 렌더링하도록 변경
- [x] `get_search_results()` — 대분류가 커스터마이징된 경우에만 소분류 커스텀 순서
      적용, 아니면 기존처럼 매칭 건수 내림차순 유지
- [x] `templates/settings.html` — 대분류를 아코디언으로, 그 안에 소분류 번호 목록 +
      ▲▼ 버튼, 커스터마이징된 대분류엔 뱃지 표시
- [x] 검증: "아이템" 그룹의 마지막 소분류(아이템샵)를 맨 위로 이동 → `/search?q=장`
      결과에서 "모험" 그룹(건드리지 않음, 여전히 건수순) 블록은 그대로, "아이템" 그룹
      블록 맨 앞에 아이템샵이 오는 것 확인(전체 순서 인덱스 21→14). 145개 라우트
      전체 스모크 테스트 재통과
- [x] CHANGELOG.md / 세션 로그 추가 기록
- [x] NAS 배포
