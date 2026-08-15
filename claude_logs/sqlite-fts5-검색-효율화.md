# 챗봇 검색 효율화 (FTS5) 세션 로그

## 요청
- 처음엔 "챗봇이 dolworld.notion.site 내용도 검색해서 반영할 수 있나" 질문으로 시작.
- dolworld.notion.site는 SPA라 정적 페치 불가 확인 → 대안으로 gvo.gamedb.info
  (일본판 大航海時代Online PukiWiki 팬위키, ~1,900페이지) 검토.
- 사용자가 외부 사이트 크롤링은 보류하고 "기존 dho_structured.sqlite3 검색/관리를
  더 효율적으로" 요청으로 방향 전환.
- 중간에 "Supabase로 옮기는 건 어떨까(백업/관리 목적)" 질문 → Turso를 대안으로 제시,
  이 논의는 보류하고 FTS5(넓은 범위: items_core + raw_attrs)로 최종 확정.

## 행동
- `chat/lib/dho-db.ts`, `dho_structured.sqlite3` 스키마/인덱스 실측 조사
  (`EXPLAIN QUERY PLAN`으로 풀스캔 확인, 인덱스 3개뿐임 확인).
- `build_search_index.py` 신규 작성 — `items_fts`(FTS5, trigram 토크나이저) 빌드,
  `items_core` + `raw_attrs`(GROUP_CONCAT) 대상.
- `dho_webapp.py`의 `DERIVED_PIPELINE_SCRIPTS`에 추가.
- `chat/lib/dho-db.ts`: `search_items`/`get_item_detail`/`get_backlinks`의 키워드
  매칭을 `findMatchingItems()` 헬퍼로 통합 + FTS5 MATCH/bm25로 교체, 3글자 미만은
  LIKE 폴백, MATCH 쿼리는 phrase(큰따옴표)로 감싸 안전하게 처리.
- 실제 DB에 빌드 실행 + 검증(속도 20배, recall 개선 실증, `npm run build`/`lint`,
  webapp 라우트 회귀 확인 전부 통과).
- `plan.md`/`checklist.md`/`context-notes.md` 갱신, 이전 세션 파일은
  `*-comma-format.md`로 보존.

## 결정
- FTS5 토크나이저는 `trigram` — 기존 `LIKE '%keyword%'` UX(부분일치)를 유지하기 위함.
- 3글자 미만 키워드는 trigram이 인덱싱 못 해서 자동으로 기존 LIKE 방식 폴백.
- MATCH 쿼리는 항상 phrase(`"..."`)로 감싸서 공백 분리/FTS5 예약어 오인식 방지.
- Supabase 이전은 무료 티어(500MB)가 이미 지금 DB(256MB)보다 여유가 부족하고
  네트워크 왕복 비용(챗봇이 턴당 도구 최대 8회 호출)이 커서 비추천, Turso(SQLite
  호환, 무료 5GB)가 더 적합하다고 판단했지만 이번 라운드에서는 보류.

## 해결된 문제
- `search_items` 등이 이름/제목에만 있는 단어로만 검색되던 한계 → raw_attrs(속성값)
  까지 검색 가능해짐 (recall 실증).
- `LIKE '%keyword%'` 풀스캔 → FTS5 인덱스 검색으로 대체(실측 최대 20배 빠름).

## 미해결
- DB 커넥션 재사용, `acquisitionInfo()` 스키마 캐시, `ANALYZE` 추가는 이번 범위 밖으로 보류.
- `openwebui_tool_dho_sql.py`(레거시)에 동일 FTS5 반영 여부 미정.
- Supabase/Turso 마이그레이션 여부 미정.
- CHANGELOG는 `[미커밋]`에 반영, 커밋은 아직 안 함(사용자 요청 시 진행).
