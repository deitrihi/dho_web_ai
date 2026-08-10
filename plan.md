# SQLite → PostgreSQL 전환 + pgvector 시맨틱 검색 + Wiki.js 문서화

## 배경
현재 서빙 스택(Flask `dho_webapp.py`, Next.js `chat/`)은 전부 `dho_structured.sqlite3`
(211개 테이블, 320MB, item_id/카테고리 구조)를 읽기 전용으로 조회한다. 이걸 PostgreSQL로
옮기고, pgvector로 시맨틱(임베딩) 검색을 추가하고, Wiki.js를 신규로 붙여서 chat이 DB와
Wiki 콘텐츠를 함께 검색하게 만드는 게 최종 목표.

## 최종 아키텍처 (2026-08-10 확정, 여러 차례 확인 거침)
- **서비스 구성**: 기존 `webapp`(Flask, 브라우징/편집)과 `chat`(Next.js, Text-to-SQL +
  시맨틱 검색)은 그대로 유지. `wikijs` 서비스를 신규 추가. `notion-sync`는 **완전
  제거**(데코미션 — Wiki.js가 생기면 개인 문서는 거기 직접 쓰면 되므로 불필요해짐).
- **백엔드 DB는 PostgreSQL 하나로 통합**: `pgvector/pgvector:pg16` 이미지 하나로 DHO
  구조화 데이터 + 벡터 임베딩을 담고, Wiki.js는 같은 인스턴스 안 별도 데이터베이스
  (`wikidb`, Wiki.js가 자체 스키마를 요구해서 DHO 데이터와는 분리)를 쓴다. webapp/chat
  모두 이 PostgreSQL 하나만 바라본다.
- **마이그레이션 범위**: `dho_structured.sqlite3`만 PostgreSQL로 옮긴다. `dho_cache.sqlite3`
  (1.5GB 원본 HTML 캐시, 재크롤링 시에만 필요)는 그대로 SQLite에 둔다.
- **파이프라인 스크립트 분리 (수정됨, 2026-08-10)**: `dho_webapp.py`가 항목 저장 때마다
  `DERIVED_PIPELINE_SCRIPTS` 8개(`build_backlinks.py`/`build_acquisition.py`/
  `materialize_generic.py`/`materialize_cannon.py`/`materialize_recipe.py`/
  `materialize_consumable.py`/`materialize_tarotcard.py`/`build_search_index.py`)를 서브프로세스로
  즉시 재실행해서 파생 테이블을 전체 재생성하는 걸 확인함 — 이 8개는 "가끔 도는 빌드"가 아니라
  **저장 시점 라이브 로직**이라 webapp이 Postgres에 쓰게 되면 반드시 같이 Postgres 대상으로
  재작성해야 함(안 그러면 저장 직후 최신 데이터가 안 보임). 반면 `build_structured_db.py`
  (원본 HTML→raw_attrs/raw_tables 파싱)와 `build_category_localization.py`는 webapp 저장 시
  재실행되지 않는, 재크롤링 시에만 도는 진짜 드문 작업이라 SQLite에 그대로 둔다.
  → **SQLite에 남는 건 이 2개뿐**, 나머지(8개 파생 스크립트 + `dho_webapp.py` +
  `chat/lib/dho-db.ts`)는 전부 Postgres 대상으로 재작성. `migrate_to_postgres.py`는 재크롤링
  후 `build_structured_db.py`/`build_category_localization.py`가 만든 `items_core`/
  `raw_attrs`/`raw_tables`/`category_localization`을 Postgres로 옮기는 다리 역할만 한다(그 뒤
  8개 파생 스크립트를 Postgres 대상으로 실행하면 나머지 파생 테이블이 채워짐).
- **chat의 검색은 DB + Wiki를 함께 다룬다**:
  - DB 쪽: 기존 SQL/키워드(`pg_trgm`) 검색 + 신규 아이템 임베딩 시맨틱 검색
    (`item_embeddings`) — 수치/관계 등 정확한 구조화 데이터 근거.
  - Wiki 쪽: Wiki.js 페이지 콘텐츠를 섹션 단위로 청킹해서 임베딩한 `wiki_chunks`
    테이블(같은 PostgreSQL) — 사람이 위키에서 직접 추가한 설명/가이드/편집 내용까지 포함한
    시맨틱 검색.
  - **grounding 규칙**: 아이템 위키 페이지 경로가 `/dho/<category>/<item_id>` 형식이므로,
    `wiki_chunks`에도 category/item_id를 같이 저장해둔다. Wiki 검색 결과가 나오면 즉시 DB
    원본 레코드와 조인해서, 최종 답변의 사실 근거는 항상 PostgreSQL 구조화 데이터가 되도록
    한다. item_id가 없는 자유 위키 페이지(공략/개요 글 등)는 청크 텍스트 자체가 근거.
  - 짧은 키워드(1~2단어)는 벡터 검색이 약할 수 있어 기존처럼 `pg_trgm`/exact match로 보완
    (지금 `FTS_MIN_LENGTH=3` 폴백 패턴과 동일한 하이브리드 유지).
  - Wiki.js **콘텐츠가 변경될 때마다** 해당 페이지를 다시 청킹·임베딩해서 `wiki_chunks`를
    갱신한다 (일괄 재동기화가 아니라 변경 시점 반영 — 구체적 트리거 방식은 Phase 3에서 결정,
    아래 리스크 참고).
- **FTS5(trigram) → PostgreSQL 매핑**: 기존 `items_fts`/`notion_fts`(SQLite FTS5 trigram
  토크나이저, 3글자 단위 부분일치)는 `pg_trgm` 확장(trigram 유사도, GIN 인덱스)으로
  대체한다. `tsvector` 전문검색은 한국어 형태소 분석기 없이는 단어 경계가 안 맞아 채택 안 함.
- **Wiki.js 자체 UI 검색**(사람이 위키를 직접 브라우징할 때 쓰는 검색창)은 PostgreSQL `db`
  검색 엔진으로 충분 — 이건 chat의 통합 검색과 별개 문제.

## 단계 순서 (의존관계상 순차 진행)
1. **Phase 1 — PostgreSQL 마이그레이션 + notion-sync 제거 (완료, NAS 배포까지)**
   - docker-compose에 postgres 서비스 추가, `migrate_to_postgres.py` 작성
   - `chat/lib/dho-db.ts`를 `pg` 드라이버로 재작성, `dho_webapp.py`를 `psycopg`로 재작성
   - `notion-sync` 서비스/스크립트/도구/문서 전체 제거
   - 기존 기능(아이템 검색/상세/백링크/SQL 실행 도구)이 PostgreSQL 위에서 동일하게 동작하는 게
     목표. **가장 큰 작업이자 이후 단계의 기반.**
2. **Phase 2 — pgvector 아이템 시맨틱 검색 (완료, NAS 배포까지)**: `item_embeddings` 테이블 + HNSW 인덱스,
   `build_embeddings.py`(OpenAI 임베딩 API 배치 호출), `chat`에 아이템 시맨틱 검색 도구 추가.
   이 단계에서 만드는 임베딩 인프라(테이블 패턴, 배치 호출 로직)를 Phase 3의 wiki 청크
   임베딩이 재사용한다.
3. **Phase 3 — Wiki.js 배포 + 콘텐츠 생성 + 청크 임베딩**
   - docker-compose에 wikijs 서비스 추가 (`wikidb` 별도 DB)
   - `build_wikijs_pages.py` — DHO 데이터 → Markdown 변환 + GraphQL Admin API 벌크 생성/갱신
     (파일럿 카테고리 먼저 → 전체 확대)
   - Wiki 콘텐츠 변경 감지 + 청킹 + 임베딩 → `wiki_chunks` 갱신 파이프라인 (웹훅 vs 주기적
     폴링은 Wiki.js 지원 범위 확인 후 Phase 3에서 결정)
   - `chat`에 Wiki 시맨틱 검색 도구 추가 + grounding 로직(청크→DB 조인)

## 리스크 / 확인 필요
- NAS(Synology) 리소스가 postgres + pgvector + wikijs + 기존 webapp/chat까지 동시에 감당
  가능한지 사전 확인 필요 (메모리/디스크 여유).
- `dho_structured.sqlite3`는 현재 NAS에서 webapp이 읽기-쓰기로 마운트하고 있음(항목
  추가/수정 기능) — Phase 1에서 webapp도 함께 PostgreSQL로 전환.
- Wiki.js가 "페이지 저장 시점" 이벤트를 웹훅으로 제공하는지 미확인 — 지원 안 하면 주기적
  폴링(`updatedAt` 비교) 방식으로 대체. Phase 3 착수 시 확인.
- 33,496개 페이지를 Wiki.js GraphQL API로 벌크 생성하는 처리량/시간 검증 필요 (Phase 3에서
  소규모 카테고리로 먼저 파일럿 후 전체 확대).
