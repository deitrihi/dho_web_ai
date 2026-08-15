# webapp 검색 기능 체크리스트

- [x] `dho_webapp.py`: `/search` 라우트 추가 — `items_search`를 `search_text ILIKE`로
      조회, 카테고리별 COUNT + 카테고리당 상위 N건(+ "외 N건 더") 구조로 반환
- [x] `templates/search.html` 신규 — 카테고리별 카드 섹션으로 결과 렌더링, 빈 검색어/
      결과 없음 상태 처리
- [x] `templates/base.html` 상단바에 검색창(GET 폼) 추가
- [x] `static/style.css` — 검색창 스타일 추가(기존 backlink-list/badge 클래스 재사용)
- [x] 스모크 테스트: Flask test_client로 검색어 몇 개(결과 많음/적음/없음/빈 문자열)
      요청해서 200 확인 — "대포" 검색이 대포/레시피/퀘스트/스킬 등 여러 카테고리로
      정상 그룹핑되는 것 확인
- [x] CHANGELOG.md `[미커밋]`에 기록
