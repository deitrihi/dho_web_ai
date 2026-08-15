# 기존 sqlite DB 검색 효율화 체크리스트

## 조사
- [x] 현재 검색 경로(`search_items`/`get_item_detail`/`get_backlinks`) 구현 확인
- [x] `EXPLAIN QUERY PLAN`으로 풀스캔 여부 실측
- [x] 인덱스/`sqlite_stat1` 존재 여부 확인
- [x] `chat/lib/dho-db.ts` 커넥션 관리 방식 확인

## FTS5 인덱스 (넓은 범위: items_core + raw_attrs)
- [x] `items_fts` 가상 테이블 스키마 설계 (name/title/description + raw_attrs를
      item당 GROUP_CONCAT한 attrs_text, trigram 토크나이저)
- [x] 인덱스 빌드 스크립트 작성/추가 (`build_search_index.py`,
      `dho_webapp.py`의 `DERIVED_PIPELINE_SCRIPTS` 마지막에 연결)
- [x] `dho_structured.sqlite3`에 실제 빌드 실행 (33,496건 적재 확인)
- [x] `searchItems`/`getItemDetail`/`getBacklinks`를 FTS5 MATCH + bm25 정렬로 교체
      (공통 로직은 `findMatchingItems()` 헬퍼로 통합, 3글자 미만 키워드는 기존 LIKE로 폴백)
- [ ] `openwebui_tool_dho_sql.py` 쪽도 동일 SQL로 반영할지 결정 (범위 밖, 보류)

## 커넥션/스키마 캐시 (이번 라운드에서는 보류 — 사용자가 FTS5만 우선 요청)
- [ ] `chat/lib/dho-db.ts` 모듈 레벨 커넥션 재사용으로 리팩터
- [ ] `acquisitionInfo()` 공유 테이블/컬럼 목록 캐시

## ANALYZE (보류)
- [ ] 빌드 파이프라인 마지막 단계에 `ANALYZE` 추가

## 검증
- [x] FTS5 전/후 검색 결과 비교 — raw_attrs에만 있는 단어("아이드/14497" 케이스)로
      검색 시 FTS는 찾고 기존 LIKE(name/title만)는 못 찾는 것 확인 (recall 향상 실증)
- [x] 응답 시간 비교 — "카노푸스" 기준 LIKE 15.6ms vs FTS 0.8ms (약 20배)
- [x] `chat/lib/dho-db.ts` 실제 함수 직접 호출 검증 (searchItems/getItemDetail,
      description 필드 보존 확인, 짧은 키워드 폴백 확인)
- [x] `npm run build`/`npm run lint` (chat) 통과
- [x] `dho_webapp.py` 기존 라우트 회귀 확인 (`/`, `/certificate`, `/certificate/1898` 200)

## 기록
- [ ] CHANGELOG.md `[미커밋]` 항목 추가
- [ ] 옵시디언 로그 append
- [ ] 커밋
