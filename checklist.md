# PostgreSQL + pgvector + Wiki.js 체크리스트

## Phase 0 — 준비 (완료)
- [x] plan.md 아키텍처 확정 (DB 통합/notion-sync 제거/wiki 청크 임베딩 grounding 포함,
      2026-08-10 사용자 확인)
- [ ] NAS 리소스(메모리/디스크) 확인 — postgres+wikijs 추가 감당 가능한지 (NAS 배포 시 확인)

## Phase 1 — PostgreSQL 마이그레이션 + notion-sync 제거 (완료, 로컬 검증까지)
### 마이그레이션
- [x] docker-compose.yml에 `postgres` 서비스 추가 (`pgvector/pgvector:pg16`, 볼륨, .env에
      `POSTGRES_*` 변수), `postgres/init.sql`로 vector/pg_trgm 확장 자동 생성
- [x] `dho_structured.sqlite3` 스키마 조사 — 실제 214개 일반 테이블, 컬럼 타입은 INTEGER/TEXT
      둘뿐. 이관 대상은 "원본성" 4개(`items_core`/`raw_attrs`/`raw_tables`/
      `category_localization`)뿐임을 확인(`staging_errors`는 아무도 안 읽어서 제외)
- [x] `migrate_to_postgres.py` 작성 — SQLite → Postgres 4개 테이블 복사(psycopg COPY 프로토콜).
      `raw_attrs`/`raw_tables`엔 SQLite rowid 대체용 `insert_seq SERIAL` 컬럼 추가
      (`ORDER BY position, rowid` 안정 정렬 재현용)
- [x] `items_fts`(FTS5) 대신 `pg_trgm` 기반 `items_search` 테이블 + GIN 트라이그램 인덱스로
      재구성 (`build_search_index.py`), `GROUP_CONCAT`→`STRING_AGG` 치환
- [x] 로컬에서 마이그레이션 실행 → items_core 33,496 / raw_attrs 149,381 / raw_tables 58,584 /
      category_localization 70건, 원본 SQLite 카운트와 일치 확인
- [x] 파생 테이블 파이프라인 8개 스크립트를 `psycopg`로 재작성 (sqlite3→psycopg,
      `DHO_DB_PATH`→`DATABASE_URL`, `?`→`%s`, `INSERT OR REPLACE`류는 원래 없어서 그대로,
      `CAST(REPLACE(x,",","" ) AS INTEGER)`처럼 SQLite가 관대하게 봐주던 큰따옴표 문자열
      리터럴을 작은따옴표로 수정 — Postgres는 큰따옴표=식별자라 그대로 두면 에러)
- [x] **버그 발견/수정 (Postgres 마이그레이션 중)**: `materialize_generic.py`가 INTEGER
      컬럼에 빈 문자열을 그대로 넣으려다 `invalid input syntax for type integer` 에러 —
      SQLite는 타입 어필리니티로 관대하게 TEXT로 저장했지만 Postgres는 엄격해서 에러남.
      빈 값은 NULL로 넣도록 수정 (`build_category_table`/`build_relation_tables` 둘 다)
- [x] **성능 문제 발견/수정**: 개별 INSERT를 수만 번 순차 실행하는 `build_acquisition.py`/
      `materialize_generic.py`가 SQLite 대비 네트워크 왕복 오버헤드로 크게 느려져
      (`build_acquisition.py` 단독 120초 초과) psycopg pipeline 모드(`conn.pipeline()`)로
      배치 전송하도록 수정 — `build_acquisition.py` 120초 초과 → 19.8초,
      `materialize_generic.py` → 43초로 개선. **다만 8개 스크립트 전체 합계는 대략
      1~2분으로, 원래 SQLite 기준 ~12초보다 훨씬 느림** — webapp 항목 저장마다 동기로
      기다리는 현재 설계상 저장 후 응답이 그만큼 오래 걸림(실측: 완전한 저장 사이클
      ~110초). 타임아웃(스크립트당 120초)은 넘기지 않지만 UX상 아쉬움 — 추후 필요하면
      백그라운드 처리나 추가 배치 최적화 검토 여지 있음(이번 범위에서는 안 함)
- [x] Postgres 위에서 8개 스크립트 전체 실행 완료, item_backlinks 440,926건/items_search
      33,496건 등 확인
- [x] `chat/lib/dho-db.ts`를 `pg`(node-postgres) 드라이버로 재작성
      - [x] `sqlite_master`/`PRAGMA table_info` 의존 로직 → `information_schema` 대응
      - [x] FTS5 MATCH+bm25 → `pg_trgm` `word_similarity()` 기반 정렬(짧은 키워드는 기존처럼
            ILIKE 폴백 유지)
      - [x] `runSql`의 서브쿼리에 별칭 추가(`AS sub`) — Postgres는 SQLite와 달리 FROM절
            서브쿼리에 별칭이 필수라 안 하면 에러
      - [x] bigint(COUNT/SUM 등) 컬럼이 문자열로 오는 pg 드라이버 기본 동작을 전역
            `types.setTypeParser(20, ...)`로 숫자 변환 (안 하면 콤마 포맷팅/LLM 숫자 연산 깨짐)
      - [ ] read-only DB 롤 이중 방어는 이번 범위에서 보류 (원래 앱단 SELECT-only 체크만
            있었고 이번에도 동일 수준 유지 — 필요시 추후 검토)
- [x] `chat/package.json`에 `pg`(+ `@types/pg`) 의존성 추가, `npx tsc --noEmit` 통과
- [x] `dho_webapp.py`를 `psycopg`로 재작성 (읽기-쓰기, `rebuild_derived_tables()` env를
      `DHO_DB_PATH`→`DATABASE_URL`, `get_write_db()`는 `next_item_id()`의 위치 인덱스 접근
      때문에 dict_row 안 씀, `get_nav_groups()`의 GROUP BY에 non-aggregate 컬럼 전부 추가
      (Postgres는 SQLite와 달리 엄격))
- [x] `requirements.txt`에 `psycopg[binary]==3.3.4` 추가
- [x] 로컬에서 webapp/chat 둘 다 Postgres 대상으로 정상 동작 확인 — 카테고리 목록/상세
      페이지(quest 11행 순서, skill 6,468건 백링크) 렌더링 확인, 항목 저장→파생 테이블
      재생성→즉시 반영 확인(Python `requests`로 클린 UTF-8 검증 — curl 셸 인코딩 문제로
      첫 시도는 깨짐, 코드 문제 아님을 확인), 챗봇 실제 질문("가나돌 사령부가 뭐야?")에
      `get_item_detail` 도구 호출→Postgres 조회→정확한 한국어 답변 생성까지 end-to-end 확인
- [x] `docker-compose.yml`의 webapp/chat 볼륨 마운트를 SQLite 파일 마운트 → `DATABASE_URL`
      환경변수로 변경, `depends_on: postgres: condition: service_healthy` 추가
- [x] `.env.example`/`.env`에 `POSTGRES_*` 추가
- [x] `deploy.sh`에 postgres 반영 (전체 배포 시 postgres+webapp+chat, exclude 주석 갱신)
- [x] `docker compose build webapp chat` 로컬 빌드 성공, 3개 서비스 동시 기동 후 컨테이너
      간 네트워크(postgres:5432 호스트명) 통신 확인

### notion-sync 제거
- [x] `docker-compose.yml`에서 `notion-sync` 서비스 정의 제거
- [x] `Dockerfile.notion-sync`, `sync_notion.py`, `sync_notion_loop.sh`,
      `scratch_notion_sync.log` 삭제
- [x] `chat/lib/dho-db.ts`의 `searchNotion()`, `chat/app/api/chat/route.ts`의 `search_notion`
      도구 등록 제거
- [x] `.env.example`/`.env`에서 `NOTION_API_KEY`/`NOTION_ROOT_PAGE` 제거
- [x] `README.md`에서 노션 동기화 관련 섹션 제거
- [x] `deploy.sh`에서 `notion-sync` 유효 서비스 인자 제거
- [x] NAS에서 기존 `dho-notion-sync` 컨테이너 정지/제거 완료

### 검증
- [x] 로컬 통합 검증 (위 항목들)
- [x] **NAS 배포 완료 (2026-08-10)** — `./deploy.sh`로 코드+.env 전송, postgres+webapp+chat
      기동. NAS 자체 OS(UGREEN)가 5432(시스템)/5433(video manager 앱)를 이미 쓰고 있어서
      포트 충돌 발견 → postgres 호스트 포트를 5434로 변경(컨테이너 내부는 그대로 5432,
      webapp/chat의 내부 `postgres:5432` 접속은 영향 없음). `docker compose up
      --remove-orphans`로 기존 `dho-notion-sync` 컨테이너 정지/제거. 로컬에서
      `migrate_to_postgres.py`를 NAS Postgres(192.168.0.200:5434)로 실행 후, NAS
      `docker compose exec webapp python <script>.py`로 파생 테이블 8개 순서대로 실행
      (내부 docker 네트워크라 로컬 테스트와 비슷한 속도). 최종 행 수 전부 로컬과 일치
      확인(items_core 33,496/raw_attrs 149,381/item_backlinks 440,926/items_search
      33,496). webapp(`/`, `/cannon/8776`)/chat(`/chat`) 전부 200, nginx-proxy 경유
      HTTPS(8443)까지 확인.

## Phase 2 — pgvector 아이템 시맨틱 검색 (완료)
- [x] `item_embeddings` 테이블 설계 (category, item_id, embedded_text, embedding vector(1536),
      PK (category, item_id)) — `build_embeddings.py`가 생성. `embedded_text`는
      `items_search.search_text`(name+title+description+attrs 통합 텍스트)를 그대로 재사용
      (이미 검색용으로 만들어둔 텍스트라 중복 로직 없이 재사용 가능하다고 판단)
- [x] `build_embeddings.py` — OpenAI 임베딩 API(`text-embedding-3-small`, 1536차원)를
      100건씩 배치 호출(REST `requests` 직접 호출, 이 프로젝트 기존 컨벤션과 동일 —
      sync_notion.py도 notion-client 대신 requests 직접 호출했음), 429/5xx는 지수백오프
      재시도. `DERIVED_PIPELINE_SCRIPTS`(저장마다 자동 재실행)엔 포함 안 함 — API
      비용/시간 때문에 수동 실행 대상
- [x] HNSW 인덱스 생성(`vector_cosine_ops`, pgvector 0.8.6에서 확인), 코사인 거리(`<=>`)
      검색 쿼리 검증
- [x] `chat/lib/dho-db.ts`에 `semanticSearchItems()` 추가 (ai-sdk `embed()` +
      `openai.textEmbeddingModel()`, route.ts와 동일하게 요청 처리 시점에 클라이언트 생성),
      `route.ts`에 `semantic_search_items` 도구 등록 + SYSTEM_PROMPT에 사용 시점 안내
- [x] **실사용 질문으로 품질 검증**: 정답을 아는 항목("가나돌 사령부", 설명에 "생산 관련
      연동을 위해 임시적으로 등록"이라고 적혀있음)을 완전히 다른 표현("제작 시스템과
      연결하려고 임시로 만들어놓은 도시")으로 질의 → 정답 항목이 유사도 1위(0.423)로 정확히
      나옴. 키워드 검색(`search_items`)은 같은 질문 그대로는 0건(예상대로 — 정확한 이름이
      아니라 개념 질문이라 키워드 검색으론 못 찾음, 시맨틱 검색의 존재 이유를 보여줌)
- [x] 로컬: 33,496건 전체 임베딩 생성 완료(약 20분 소요, 비용 미미 — text-embedding-3-small
      $0.02/1M 토큰). 이전 테스트 잔여물(item_id 900000000)이 `items_search`에 안 지워져
      있던 걸 발견해서 정리(로컬 전용 이슈, NAS엔 없었음)
- [x] NAS: `./deploy.sh`로 코드 배포 후 `docker compose exec webapp python
      build_embeddings.py`로 NAS Postgres에도 전체 임베딩 생성

## Phase 3 — Wiki.js 배포 + 콘텐츠 생성 + 청크 임베딩 (미착수)
- [ ] docker-compose.yml에 `wikijs` 서비스 추가 (`ghcr.io/requarks/wiki:2`), Postgres 안에
      별도 DB(`wikidb`) 생성
- [ ] Wiki.js 초기 설정(관리자 계정, 검색 엔진을 PostgreSQL `db` 엔진으로 설정)
- [ ] `build_wikijs_pages.py` — DHO 데이터 → Markdown 변환 + GraphQL Admin API 벌크
      생성/갱신, 소규모 카테고리로 파일럿 먼저
- [ ] 파일럿 검증 후 70개 카테고리 전체로 확대
- [ ] Wiki.js 페이지 저장 시점 웹훅 지원 여부 확인 → 지원 시 웹훅, 미지원 시 주기적 폴링으로
      "변경 시 재청킹" 파이프라인 설계
- [ ] `wiki_chunks` 테이블 설계 (page_path, category nullable, item_id nullable, chunk_index,
      chunk_text, embedding)
- [ ] Markdown 섹션 단위 청킹 로직 (설명/속성블록/표/획득처 등 헤더 기준)
- [ ] 변경 감지 → 청킹 → 임베딩 → upsert 파이프라인 구현
- [ ] `chat/lib/dho-db.ts`에 Wiki 시맨틱 검색 함수 추가 (category/item_id 있으면 DB 원본
      레코드와 조인해서 grounding), `route.ts`에 도구 등록
- [ ] NAS 배포, deploy.sh 반영
- [ ] 최종 사용자 확인

## 문서화
- [x] README.md에 새 아키텍처(Postgres, notion-sync 제거) 반영, 데이터 파이프라인 절 갱신
- [ ] CHANGELOG.md `[미커밋]`에 기록
- [ ] claude_logs 세션 로그 기록
