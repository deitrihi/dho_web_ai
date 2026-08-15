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

## Phase 3 — Wiki.js 배포 + 콘텐츠 생성 + 청크 임베딩 (진행 중, 2026-08-10 착수)
- [x] docker-compose.yml에 `wikijs` 서비스 추가 (`ghcr.io/requarks/wiki:2`), Postgres 안에
      별도 DB(`wikidb`) 생성. 기존 볼륨(postgres_data)이 이미 있는 배포에선
      `postgres/init.sql`이 재실행되지 않으므로 `CREATE DATABASE wikidb;`를 수동 1회 실행
      필요(로컬은 `docker exec dho-postgres psql ... -c "CREATE DATABASE wikidb;"`로 완료,
      NAS 배포 시에도 동일하게 필요)
- [x] Wiki.js 초기 설정 자동화 — 공식 이미지(`ghcr.io/requarks/wiki`)는 검색 결과에 나온
      `ADMIN_EMAIL`/`ADMIN_PASS` 환경변수를 지원하지 않음(그건 별도 서드파티 포크 얘기였음,
      실제로는 "DB Configuration is empty... Switching to Setup mode"로 항상 브라우저
      마법사를 요구). 대신 `server/setup.js` 소스를 직접 확인해서 마법사가 하는 일이
      `POST /finalize` 요청 하나(JSON body: adminEmail/adminPassword/siteUrl/telemetry)임을
      확인, curl/Python으로 브라우저 없이 그대로 재현 — 완전 자동화됨. 검색 엔진은 Wiki.js
      기본값(`db`, PostgreSQL 기반)을 그대로 씀
- [x] GraphQL API 인증 — API 토큰(Admin UI 발급, 브라우저 필요) 대신
      `authentication.login` mutation으로 JWT 발급받아 사용(기본 만료 30분이라
      `build_wikijs_pages.py`가 20분마다 자동 재로그인). `pages.create`/`pages.update`/
      `pages.singleByPath` 스키마는 GraphQL introspection으로 실제 검증(검색 결과로 얻은
      필드 목록과 거의 일치했지만 introspection으로 최종 확인)
- [x] `build_wikijs_pages.py` — DHO 데이터 → Markdown 변환(속성은 `## 속성` 리스트, 표는
      `### <표 이름>` 마크다운 표, 원본 raw_attrs.links_json을 위키 경로
      `/dho/<category>/<item_id>` 링크로 치환 — dho_webapp.py의 `render_text_with_links()`와
      동일 로직) + GraphQL 벌크 생성/갱신. `wiki_page_state`(로컬 DB) 테이블에 콘텐츠 해시를
      저장해서 변경 없는 항목은 재요청 스킵(idempotent, 재실행 안전)
- [x] 파일럿 카테고리(tarotCard 22건, dungeon 35건 — dungeon은 링크+표+이미지 전부 있는
      대표 케이스)로 검증. GraphQL 응답을 curl(Git Bash)로 확인했을 때 한글이 깨져 보여서
      처음엔 인코딩 버그로 의심했으나, `wikidb.pages`에서 hex로 직접 대조한 결과 실제 DB엔
      정상 UTF-8로 저장되어 있었음 — Git Bash 콘솔 표시 문제였을 뿐 실제 데이터는 문제
      없었음. 이후 스크립트/테스트는 전부 Python으로 진행(memory: 이 환경 curl 한글 이슈).
      링크/표/이미지 렌더링 전부 육안 확인 완료
- [x] Wiki.js 페이지 저장 시점 웹훅 지원 여부 확인 — **미지원 확정**(2026-08 기준
      requarks/wiki 이슈 트래커에 기능 요청으로만 존재, 아직 구현 안 됨). 주기적 폴링으로
      확정: `wikidb.pages.hash`(Wiki.js가 저장 시점마다 갱신하는 내부 콘텐츠 해시)를
      `wiki_chunk_sync_state`와 비교해서 바뀐 페이지만 재청킹하는 방식으로 구현
- [x] `wiki_chunks` 테이블 구현 (page_path, category nullable, item_id nullable,
      chunk_index, chunk_text, embedded_text, embedding vector(1536), HNSW 인덱스) +
      `wiki_chunk_sync_state`(page_path, content_hash) 폴링 상태 테이블
- [x] Markdown 섹션 단위 청킹 로직 (`#`/`##`/`###` 헤더 기준 정규식 분할 — attrs 전체가
      "## 속성" 청크 하나, 표는 "### <표 이름>"마다 별도 청크). 임베딩 입력엔 페이지 제목을
      접두어로 붙여 문맥 보강(item_embeddings의 embedded_text 패턴과 동일)
- [x] `build_wiki_chunks.py` — 콘텐츠는 항상 wikidb(Wiki.js가 실제 서빙하는 DB)에서
      읽음(사람이 위키에서 직접 편집한 내용도 반영되도록, build_wikijs_pages.py가 만든
      마크다운을 재사용하지 않음). 삭제된 페이지의 청크도 정리. 재실행 시
      idempotent(해시 동일하면 스킵) 확인 완료
- [x] 종단간 검증(로컬): pilot 58페이지 → 250청크 임베딩 → "이집트 피라미드 안에서 탐험할
      수 있는 유적" 자연어 질의 → "기자 피라미드 중계층" 정확히 1위로 검색됨 확인
- [x] `chat/lib/dho-db.ts`에 `semanticSearchWiki()` 추가 (category/item_id 있으면 items_core
      원본 레코드와 조인해서 grounded_item으로 반환), `route.ts`에 `semantic_search_wiki`
      도구 등록 + 시스템 프롬프트에 "사실 근거는 항상 grounded_item 우선, chunk_text는
      보조 설명" 규칙 명시. `npm run build` 타입체크 통과 + 실제 chat API로 종단간 테스트
      (기자 피라미드 던전 질문 → semantic_search_wiki 호출 → grounded_item 포함 정확한
      답변 확인)
- [x] 70개 카테고리 전체(33,496건) 백필 완료(2026-08-10~14). Wiki.js 2.5.314의
      동시 쓰기(rebuild-tree) 버그로 실제 쓰기만 전역 락으로 직렬화하도록 수정,
      로컬 Docker Desktop이 중간에 다운돼서 프로세스가 죽었다가 복구(볼륨 덕분에 데이터
      손실 없음, idempotent라 재실행으로 이어감), 페이지가 누적될수록 Wiki.js 저장이
      느려지며 생긴 타임아웃 413건은 `WIKIJS_REQUEST_TIMEOUT` 상향(30→90초) 재시도로
      전부 해소. 최종 실패 0건.
- [x] `build_wiki_chunks.py` 전체 실행 완료 — 33,439개 변경 페이지 → 125,328개 청크
      임베딩(2026-08-14)
- [x] NAS 배포 완료(2026-08-11 인프라, 2026-08-14~15 데이터 반영). `./deploy.sh`(전체
      서비스)로 코드 배포 + `wikijs` 서비스 기동, `wikidb` 수동 생성, `POST /finalize`로
      설치 마법사 완료. 페이지/청크 데이터는 로컬에서 재백필하지 않고 `pg_dump`
      (custom format, `wikidb` 전체 + `dho` DB의 `wiki_chunks`/`wiki_page_state`/
      `wiki_chunk_sync_state` 3개 테이블만)로 로컬 검증본을 그대로 NAS로 이관, `pg_restore
      --clean --if-exists`로 복원(NAS SCP는 신형 SFTP 프로토콜에서 "No such file or
      directory"가 나서 `scp -O`로 구버전 프로토콜 사용 필요했음). NAS `semantic_search_wiki`
      실제 질문으로 재검증 완료(grounded_item 포함 정상 응답 확인)

## Phase 4 — 위키 브라우징 진입점 + 자유 문서 지원 (2026-08-15, 로컬 완료)
- [x] `build_wikijs_pages.py`에 카테고리 인덱스(`dho/<category>`) 생성 로직 추가 — 항목 목록
      + 링크
- [x] `build_wikijs_pages.py`에 루트 인덱스(`dho`) 생성 로직 추가 — 대분류별 카테고리 목록
      + 링크 (`category_localization` 재사용)
- [x] `guides` stub 페이지 생성 로직 추가 (자유 문서용 앵커)
- [x] Wiki.js Navigation에 `/dho`, `/guides` 항목 자동 등록(멱등, 기존 트리 보존) — GraphQL
      introspection으로 `navigation.tree`/`updateTree` API 확인 후 구현
- [x] 로컬 Wiki.js에서 실행 후 홈→카테고리→항목 클릭 탐색 확인 (파일럿 tarotCard HTTP 200
      확인 → `--all`로 전체 70개 카테고리 인덱스 백필, 실패 0건, 최대 카테고리 quest(5,052건)
      페이지도 정상 서빙 확인)
- [x] 자유 위키 문서가 chat 검색에 반영되는지 확인 — `build_wiki_chunks.py`가 이미 경로
      제한 없이 전체 페이지를 청킹하고 있어서 **추가 구현 불필요함을 코드 확인으로 결론**
- [x] NAS 반영 — `build_wikijs_pages.py --all` 재실행으로 인덱스/guides/Navigation 반영
      완료(2026-08-16)
- [x] NAS `/dho` 등 접두어 없는 경로 접근 시 404 — 원인은 사이트 기본 locale(ko)과 페이지
      locale(en 하드코딩) 불일치였음(namespacing 문제 아니었음). 페이지 locale을 ko로
      마이그레이션(로컬+NAS 양쪽 wikidb `pages`/`pageTree`/`pageHistory`/`pageLinks`
      일괄 UPDATE + `build_wikijs_pages.py` locale 하드코딩 수정), 양쪽 `/dho`,
      `/dho/tarotCard/8611`, `/guides` 200 확인 완료 — 상세는 `context-notes.md`
      2026-08-16 항목
- [x] "/" 접속 시 "Welcome to your wiki" 초기 화면 대신 `/dho`로 리다이렉트 — Wiki.js에
      홈페이지 지정 설정 자체가 없어서 `scriptJs`(공식 지원 페이지별 커스텀 JS)로
      `window.location.replace('/dho')` 실행. 처음 `path=""`에 만들었다가 안 먹혀서
      Wiki.js 소스 확인 결과 "/"는 내부적으로 `path="home"`으로 정규화됨을 확인, `move`
      mutation으로 재배치해서 해결. 로컬+NAS 둘 다 `<page path="home">` 렌더링 확인 —
      상세는 `context-notes.md` 2026-08-16 항목
- [ ] 홈페이지를 리다이렉트 대신 정적 2-링크 콘텐츠로 전환 + 홈 전용 `scriptCss`로 좌측
      사이드바 숨김. 로컬+NAS DB 반영 확인 완료, `scriptJs` 제거. 실제 브라우저에서 여백 없이
      깔끔하게 렌더링되는지 사용자 확인 대기 중(Vuetify padding 보정이 안 맞을 수 있음) —
      상세는 `context-notes.md` 2026-08-16 항목

## Phase 5 — 링크 도우미 `/link/<이름>` (2026-08-16)
- [x] `dho_webapp.py`에 `/link/<name>` 라우트 + `get_link_matches()` 추가 — `items_core`
      `COALESCE(name, title)` 정확 매칭, 1건이면 Wiki.js 문서로 302, 여러/0건이면
      `templates/link_result.html`로 목록/안내 렌더링
- [x] `.env.example`에 `WIKIJS_PUBLIC_URL` 추가(리다이렉트용 브라우저 접속 주소, 기존
      스크립트용 `WIKIJS_URL`과 분리)
- [x] 로컬 스택(`dho-webapp`/`dho-postgres`/`dho-wikijs` 컨테이너)에 반영 후 3가지 케이스
      실측 검증: 유일 매칭("귀족의 모닥불" → consumable/2964582로 302, 리다이렉트 대상
      200 확인), 복수 매칭("알렉산드리아" → city/discovery 2건 목록), 매칭 없음(안내 메시지)
- [ ] NAS `.env`에 실제 `WIKIJS_PUBLIC_URL`(브라우저에서 접속하는 실주소) 채워넣기 — 사용자
      확인/작업 필요
- [ ] NAS 재배포 후 실제 Wiki.js 문서에 `[텍스트](/link/이름)` 링크를 넣어 클릭 테스트

## 문서화
- [x] README.md에 새 아키텍처(Postgres, notion-sync 제거) 반영, 데이터 파이프라인 절 갱신
- [x] CHANGELOG.md `[미커밋]`에 기록
- [x] claude_logs 세션 로그 기록
