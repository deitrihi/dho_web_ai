# webapp 검색 기능

## 배경
`dho_webapp.py`(조회용 Flask 웹앱)는 카테고리 목록 → 항목 목록 → 상세 3단 구조뿐이라,
카테고리를 모르면 원하는 항목을 못 찾음. 사용자 요청: 검색 기능 추가, LIKE 검색이면
충분, 결과는 카테고리별로 정리.

## 접근 방식
- 새 쿼리/인덱스를 만들지 않는다. 챗봇용으로 이미 구축된 `items_search` 테이블
  (`build_search_index.py`, `category`/`item_id`/`name`/`title`/`search_text` +
  `pg_trgm` GIN 인덱스, `name`+`title`+`description`+`raw_attrs` 속성값까지 포함)을
  그대로 재사용한다. `search_text ILIKE '%keyword%'`로 조회 — 사용자가 요청한 "LIKE
  검색"에 부합하면서 이미 인덱싱된 테이블이라 성능도 확보됨. `chat/lib/dho-db.ts`의
  기존 패턴(`ILIKE $1 on search_text`)과도 동일해서 검색 결과가 챗봇과 webapp 사이에
  일관됨.
- 결과 그룹핑은 기존 `get_backlinks()` 패턴(카테고리별 COUNT → 카테고리별 상위 N건 +
  "외 N건 더")을 그대로 따라간다. 이미 검증된 UI/쿼리 구조라 재사용.
- 새 라우트 `/search?q=` 추가, `templates/search.html` 신규, `base.html` 상단바에
  검색창 추가.

## 범위 밖
- 새 검색 인덱스/스키마 변경 없음 (`items_search` 그대로 사용).
- 페이지네이션/정렬 옵션 없음 — 카테고리당 상위 N건 노출로 충분하다고 판단(요청 범위 밖).
- 관련도 랭킹(bm25 등)은 안 함 — 요청이 "LIKE 검색이면 될 것 같다"였으므로 단순 매칭만.
