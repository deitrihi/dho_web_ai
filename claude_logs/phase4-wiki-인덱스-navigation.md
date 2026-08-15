# Phase 4 — 위키 브라우징 진입점 + 자유 문서 지원 (2026-08-15)

## 요청
- 위키 홈 화면/사이드바에서 아무것도 안 보임 — 원인 확인 및 해결
- 추가: `webapp`엔 넣기 애매한 자유 형식 팁/공략 글을 위키에 직접 쓰고 싶고, chat 검색에도
  반영되길 원함

## 행동
1. `build_wikijs_pages.py`/`build_wiki_chunks.py`/`plan.md` 재확인 — 항목 낱개 페이지만
   생성했을 뿐 인덱스/Navigation은 애초에 만든 적이 없었음을 확인
2. `build_wiki_chunks.py`가 `wikidb.pages` 전체를 경로 제한 없이 읽는 것 확인 → 자유 문서
   요구사항은 이미 지원됨(추가 구현 불필요, `chat/lib/dho-db.ts`의 `semanticSearchWiki()`도
   category/item_id NULL 케이스를 이미 처리)
3. Wiki.js GraphQL 스키마 introspection으로 `navigation.tree`/`navigation.updateTree` 확인
4. `build_wikijs_pages.py`에 추가:
   - `build_root_index_markdown()` / `sync_root_index()` — `dho` 경로, 대분류별 카테고리
     목록(`category_localization` 재사용)
   - `build_category_index_markdown()` / `sync_category_index()` — `dho/<category>` 경로,
     카테고리 내 전체 항목 링크
   - `GUIDES_STUB_CONTENT` / `sync_guides_stub()` — `guides` 경로, 자유 문서 안내 페이지
   - `ensure_navigation()` — 사이드바에 "DHO 아카이브"(`/dho`)/"가이드 / 팁"(`/guides`)
     자동 등록(기존 항목 보존)
5. 로컬 파일럿(`--categories tarotCard`) → GraphQL/DB 직접 조회 + HTTP GET으로 검증 →
   `--all`로 나머지 69개 카테고리 인덱스 백필

## 결정
- 인덱스 페이지(최대 71개)는 해시 스킵 로직 없이 매번 upsert — 새 상태 테이블 안 만들고
  단순하게 감
- 카테고리 인덱스는 flat 링크 목록(최대 5,052건까지도 페이지네이션 없이) — 상세 페이지도
  이미 큰 표를 다루고 있어 문제없다고 판단

## 해결된 문제
- 홈 → DHO 아카이브 → 카테고리 → 항목 클릭 탐색 확보 (전부 HTTP 200 확인)
- 자유 위키 문서의 chat 검색 반영 — 기존 파이프라인으로 이미 지원됨을 확인만 함

## 후속 (같은 날, 사용자 요청)
- NAS 반영은 사용자가 다른 세션에서 이미 진행함
- em dash(—) 콘솔 인코딩 버그 수정 요청 → `build_wikijs_pages.py` import 직후
  `sys.stdout.reconfigure(encoding="utf-8")`/`sys.stderr.reconfigure(...)` 추가.
  `--categories tarotCard` 재실행으로 마지막 요약 줄까지 정상 출력 + exit code 0 확인

## 미해결
- 없음
