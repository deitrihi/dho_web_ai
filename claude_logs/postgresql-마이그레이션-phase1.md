# PostgreSQL 마이그레이션 Phase 1 세션 로그

## 요청
- SQLite(`dho_structured.sqlite3`) 기반 아키텍처를 PostgreSQL로 전환하고, 이후 pgvector
  시맨틱 검색 + Wiki.js 문서화까지 이어갈 계획.
- 확인 과정에서 확정된 방향: webapp/chat 유지 + Wiki.js 신규 추가, DB는 PostgreSQL 하나로
  통합, chat이 DB+Wiki를 함께 검색(Wiki 콘텐츠는 청킹해서 pgvector에 저장, category/item_id로
  DB와 grounding), notion-sync 기능은 완전 제거.
- 이번 세션 범위는 Phase 1(PostgreSQL 마이그레이션)까지.

## 행동
- `plan.md`/`checklist.md`/`context-notes.md` 신규 작성(기존 노션 연동 문서는
  `*-notion-sync.md`로 보존).
- docker-compose.yml에 `postgres`(`pgvector/pgvector:pg16`) 서비스 추가,
  `postgres/init.sql`로 vector/pg_trgm 확장 자동 생성.
- notion-sync 관련 파일(`Dockerfile.notion-sync`/`sync_notion.py`/`sync_notion_loop.sh`)과
  코드(`searchNotion`/`search_notion` 도구) 전체 삭제.
- `migrate_to_postgres.py` 신규 — SQLite의 "원본성" 4개 테이블(items_core/raw_attrs/
  raw_tables/category_localization)만 Postgres로 이관.
- 파생 테이블 8개 스크립트(build_backlinks/build_acquisition/materialize_*(5개)/
  build_search_index)를 sqlite3 → psycopg로 재작성. FTS5는 pg_trgm 기반 `items_search`
  테이블로 교체.
- `chat/lib/dho-db.ts`를 `node:sqlite` → `pg`(node-postgres)로 재작성.
- `dho_webapp.py`를 sqlite3 → psycopg(dict_row)로 재작성.
- 로컬 Docker로 postgres 띄워서 전체 파이프라인 실행 + webapp/chat 스모크 테스트 +
  실제 챗봇 질문 end-to-end 검증.

## 결정
- SQLite는 `build_structured_db.py`/`build_category_localization.py`(재크롤링 시에만 도는
  드문 작업)에만 남기고, `dho_webapp.py`가 저장 때마다 재실행하는 파생 테이블 8개 스크립트는
  전부 Postgres 대상으로 전환 — webapp의 실시간 재생성 로직을 발견하고 나서 애초 계획("8개
  스크립트는 SQLite에 그대로 둔다")을 정정함.
- Wiki.js 검색과 벡터 검색을 분리하려던 초기 판단은 사용자가 "chat에서 DB+Wiki를 함께
  검색하고 싶다"고 명확히 하면서 폐기, Wiki 콘텐츠도 청킹+임베딩해서 pgvector로 검색하는
  방향으로 변경(Phase 3에서 구현 예정).

## 해결된 문제
- Postgres의 엄격한 타입 검사로 드러난 버그 2건: INTEGER 컬럼에 빈 문자열 삽입 시도
  (`materialize_generic.py`), SQLite가 관대하게 봐주던 큰따옴표 문자열 리터럴
  (`dho_webapp.py`의 CAST/REPLACE, `runSql`의 서브쿼리 별칭 누락).
- 개별 INSERT 수만 건으로 인한 성능 저하(120초 타임아웃) — psycopg pipeline 모드로 해결
  (`build_acquisition.py` 19.8초, `materialize_generic.py` 43초).
- pg 드라이버가 bigint를 문자열로 반환하는 기본 동작 — 전역 타입 파서로 수정.

## 미해결
- **8개 파생 스크립트 전체 실행 시간 합계가 약 1~2분**으로 원래 SQLite 기준(~12초)보다
  훨씬 느림 — webapp 항목 저장이 동기로 이걸 기다리는 구조라 저장 응답이 ~110초까지
  걸림(타임아웃은 안 넘지만 UX 저하). 사용자에게 아직 확인 안 함 — 다음에 "저장이 느리다"는
  얘기가 나오면 이 항목부터 볼 것(해결책 후보: 비동기 백그라운드 재생성).
- Phase 2(pgvector 아이템 임베딩)/Phase 3(Wiki.js) 미착수.

## NAS 실배포 (같은 세션, 이어서 진행)
사용자가 "nas 배포로 넘어가자"고 해서 이어서 진행. SSH 접근 가능 확인 후(이전 세션 기록엔
"SSH 접근 없어 대행 불가"였는데 이번엔 됨) 직접 배포.

- `./deploy.sh` 실행 중 NAS(UGREEN OS)가 이미 네이티브 PostgreSQL을 5432(시스템)/
  5433(video manager 앱)에서 쓰고 있어서 postgres 컨테이너 포트 바인딩 실패 — `docker ps`엔
  안 보이는 네이티브 프로세스라 `ps aux`로 원인 파악. 5434로 변경해서 해결(컨테이너 내부
  포트는 그대로라 webapp/chat 접속엔 영향 없음, 로컬 docker-compose.yml도 같이 5434로 바뀜).
- `docker compose up --remove-orphans`로 기존 `dho-notion-sync` 컨테이너 제거.
- 로컬에서 `migrate_to_postgres.py`를 NAS Postgres(LAN 직접 접속)로 실행, NAS에서는
  `docker compose exec webapp python <script>.py`로 파생 테이블 8개를 컨테이너 내부
  네트워크로 실행(로컬 테스트와 비슷한 속도).
- 최종 행 수 전부 로컬과 일치, webapp/chat/nginx-proxy 경유 HTTPS(8443)까지 정상 확인.
- 배포 과정에서 기존 운영 중이던 webapp/chat이 컨테이너 재생성으로 잠깐 다운됐다가
  복구됨(포트 충돌 해결 전까지 수 분).

### 미해결 (배포 후)
- NAS 실사용 테스트(다양한 실제 질문)는 사용자 몫.

## Phase 2 — pgvector 아이템 시맨틱 검색 (같은 세션, 이어서 진행)
사용자가 "Phase2로 넘어가줘"로 진행 지시. 별도 확인 질문 없이 plan.md에 이미 있던 설계대로
바로 구현(OpenAI 임베딩, text-embedding-3-small) — 비용이 미미하고 언제든 재생성 가능한
결정이라 판단.

### 행동
- `build_embeddings.py` 신규 — `items_search.search_text`(이미 만들어둔 통합 텍스트)를
  재사용해서 OpenAI 임베딩 API(text-embedding-3-small, 1536차원)로 100건씩 배치 호출,
  `item_embeddings` 테이블(HNSW 코사인 인덱스)에 저장. `requests` 직접 호출(openai 패키지
  의존성 추가 안 함, sync_notion.py와 동일 컨벤션). 저장마다 자동 재실행되는
  DERIVED_PIPELINE_SCRIPTS엔 포함 안 함(API 비용/시간 때문).
- `chat/lib/dho-db.ts`에 `semanticSearchItems()` 추가(ai-sdk `embed()`), route.ts에
  `semantic_search_items` 도구 등록.
- 로컬 33,496건 + NAS 33,496건 전체 임베딩 생성(각 20~40분).

### 품질 검증 방법 (재사용 가능한 패턴으로 기록)
게임 도메인 지식이 없어서 임의 질문으로는 결과 품질 판단이 어려웠음 → 이미 정답을 아는
항목(가나돌 사령부, 설명에 "생산 관련 연동을 위해 임시적으로 등록")을 완전히 다른 표현
("제작 시스템과 연결하려고 임시로 만들어놓은 도시")으로 질의해서 정답이 상위에 나오는지
확인하는 방식을 씀 — 실제로 유사도 1위(0.423)로 정확히 나와서 검증 성공.

### 해결된 문제
- 로컬 items_search에 Phase 1 테스트 때 남은 잔여 행(item_id 900000000)이 안 지워져
  있던 걸 발견, 정리(로컬 전용 이슈, NAS엔 없었음).

### 미해결
- Phase 3(Wiki.js) 미착수.
- Phase 2/3는 여전히 미착수.
