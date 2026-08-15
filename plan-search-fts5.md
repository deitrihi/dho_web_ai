# 기존 sqlite DB 검색 효율화

## 배경
챗봇(`chat/lib/dho-db.ts`, `openwebui_tool_dho_sql.py`)이 `dho_structured.sqlite3`를
조회하는 방식을 점검한 결과 아래 비효율이 확인됨.

1. `search_items`/`get_item_detail`/`get_backlinks`가 전부
   `WHERE name LIKE '%keyword%' OR title LIKE '%keyword%'` 방식만 사용.
   - leading wildcard라 인덱스를 못 씀 → 매번 `items_core`(33,496행) 풀스캔
     (실측 `EXPLAIN QUERY PLAN` = `SCAN items_core`, 단순 조회도 ~36ms).
   - 관련도 순위가 없음 — 물리적 저장 순서로 앞 10~30건만 반환.
   - `description`(설명문)과 `raw_attrs`(속성값, 149,381행)는 검색 대상에서
     아예 빠져있음 — 이름/제목에 없는 단어로는 못 찾음.
2. `chat/lib/dho-db.ts`의 모든 export 함수가 호출마다 `new DatabaseSync()`로
   커넥션을 새로 열고 `finally`에서 닫음 — 한 채팅 턴에 도구가 여러 번
   불릴 수 있는데 매번 파일 열기/스키마 로드 비용이 붙음.
3. `acquisitionInfo()`가 `get_item_detail` 호출마다 `sqlite_master`를 다시 조회하고,
   찾은 공유 테이블마다 `PRAGMA table_info`를 매번 실행 — 스키마는 read-only라
   안 변하는데 매번 재계산.
4. `sqlite_stat1`(ANALYZE 통계)이 없어 쿼리 플래너가 최적 실행계획을 못 세울 수 있음.

## 목표
- 검색 품질: 이름/제목뿐 아니라 설명·속성값까지 검색되고, 관련도순으로 정렬되게 한다.
- 검색 속도: leading-wildcard 풀스캔을 인덱스 기반 검색으로 대체한다.
- 관리: DB가 재생성될 때(`build_structured_db.py` → `materialize_*.py` 파이프라인)
  검색 인덱스도 자동으로 함께 갱신되게 한다.

## 접근 방식
1. **FTS5 가상 테이블 도입** (핵심)
   - `items_fts`: `items_core`의 `name`/`title`/`description` + 필요시 연결된
     `raw_attrs.text`까지 인덱싱.
   - `MATCH` + `bm25()`로 관련도순 정렬. `search_items`/`get_item_detail`/
     `get_backlinks`의 LIKE 검색을 FTS5 MATCH로 교체.
   - 빌드 스크립트(`dho_webapp.py`의 `rebuild_derived_tables()` 순서 끝,
     또는 별도 `build_search_index.py`)에 FTS5 재구축 단계 추가 — 원본
     데이터 파이프라인 재실행 시 검색 인덱스도 항상 최신 유지.
2. **DB 커넥션 재사용**: `chat/lib/dho-db.ts`에서 모듈 로드 시 1회만 연결하고
   재사용 (매 호출 open/close 제거).
3. **acquisitionInfo 스키마 캐시**: 공유 테이블 목록/컬럼을 모듈 레벨에 캐시.
4. **ANALYZE 실행**: 빌드 파이프라인 마지막 단계에 추가.

## 범위 밖
- 앞서 논의했던 dolworld.notion.site / GVO 위키 외부 크롤링은 이번 작업에서 제외
  (사용자가 "일단 잊고 기존 DB 효율화부터"로 방향 전환함).
- `openwebui_tool_dho_sql.py`는 레거시 경로(현재 `chat/`이 메인 프론트)라 FTS5 SQL은
  공유하되 커넥션 재사용 리팩터는 `chat/lib/dho-db.ts`만 우선 적용 — 필요시 후속 논의.

## 검증
- FTS5 도입 전/후 동일 키워드로 `search_items` 결과 비교(품질 향상 확인 —
  예: description에만 등장하는 단어로 검색했을 때 이제 찾아지는지).
- 대량 키워드로 응답 시간 비교(LIKE 풀스캔 vs FTS5 MATCH).
- `chat`에서 `npm run build`/`npm run lint` 통과.
- 기존 웹앱(`dho_webapp.py`) 라우트 회귀 없는지 확인(검색 인덱스는 챗봇 전용이라
  webapp 경로는 영향 없어야 함 — 확인 차원).
