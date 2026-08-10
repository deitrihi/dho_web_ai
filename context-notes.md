# PostgreSQL + pgvector + Wiki.js — 결정 사항 로그

## 2026-08-10 | 요구사항 확정
사용자가 "SQLite → PostgreSQL 전환 + pgvector 벡터 DB 구축 + NAS에서 Wiki.js 띄워서 검색"을
요청. 세 갈래로 해석될 수 있는 지점이 있어 AskUserQuestion으로 확인.

- **Wiki.js 역할**: 3개 선택지(① DHO 데이터를 위키 문서화 ② 기존 챗봇을 위키에 임베드
  ③ 완전히 별개 용도) 중 ①(추천) 선택. → Wiki.js가 Flask 웹앱의 "브라우징" 역할을 대체하는
  방향으로 확정. 기존 `dho_webapp.py`를 완전히 걷어낼지, 당분간 병행할지는 아직 미정 — Phase 3
  착수 시 다시 확인 필요.
- **마이그레이션 범위**: `dho_structured.sqlite3`만(추천) 선택. `dho_cache.sqlite3`(원본 HTML
  캐시, 재크롤링용)는 SQLite에 유지.
- **임베딩 소스**: OpenAI 임베딩 API(추천) 선택. 로컬 임베딩 모델(Ollama 등)은 채택 안 함.

## 아키텍처 판단 — SQLite를 빌드 산출물로 유지
스크래핑→파싱 파이프라인(8개 스크립트: `build_structured_db.py`, `materialize_*.py` 5개,
`build_acquisition.py`, `build_backlinks.py`, `build_search_index.py`,
`build_category_localization.py`)은 이미 검증된 SQLite 기반 코드라, 전부 Postgres로
재작성하는 대신 "SQLite = 빌드 산출물, Postgres = 서빙 DB"로 역할을 나누고 `migrate_to_postgres.py`
하나로 동기화하는 방식을 계획에 반영함(→ [[dho-project-overview]]의 파이프라인 흐름과 호환).
아직 사용자에게 최종 확인은 안 받은 상태 — plan.md에 "제안 — 진행 전 확인 필요"로 표시해둠.
대안(8개 스크립트 전체 Postgres 재작성)은 회귀 위험/작업량이 커서 기본안으로 채택 안 함.

## FTS5 → pg_trgm 매핑 판단
기존 `items_fts`/`notion_fts`는 SQLite FTS5의 trigram 토크나이저로 부분일치 검색을 하고
있었음(`chat/lib/dho-db.ts`의 `FTS_MIN_LENGTH = 3` 상수와 주석 참고 — 한국어에 형태소 분석기
없이 3글자 단위로 자름). PostgreSQL의 `tsvector` 전문검색은 한국어 형태소 분석 사전이 없으면
단어 경계 기준이 달라져 기존 검색 동작과 어긋날 가능성이 큼 → `pg_trgm` 확장(trigram 유사도)이
직접적인 동등 대체재로 판단, 이걸 기본안으로 계획에 반영.

## Wiki.js 검색과 벡터 검색 역할 분리 (→ 아래 항목에서 수정됨)
Wiki.js 코어의 검색 엔진 확장 포인트에 커스텀 pgvector 프로바이더를 끼우는 건 공식 지원
범위 밖(포크 없이는 어려움)이라고 판단 — Wiki.js 자체 검색(PostgreSQL `db` 엔진)은 위키
페이지 콘텐츠 대상 키워드 검색만 담당하고, pgvector 시맨틱 검색은 `chat/`(Next.js 챗봇)
쪽에만 도구로 추가하는 것으로 역할을 나누려 했음. **이후 사용자가 "chat에서 검색할 때 DB와
Wiki가 같이 검색되었으면 좋겠다"고 명확히 해서 이 판단은 수정됨** — 아래 "chat 통합 검색 +
grounding" 항목 참고. Wiki.js 자체 UI의 검색창(사람이 위키를 직접 브라우징할 때)에 대한
판단(=PostgreSQL `db` 엔진으로 충분)만 유효하게 남음.

## 이전 세션 미완료 작업 보존
착수 전 기존 `plan.md`/`checklist.md`/`context-notes.md`(노션 데이터 챗봇 검색 연동, 거의
완료 — NAS 배포/실사용 확인만 남음)를 `*-notion-sync.md`로 이름 변경해서 보존함. 그 작업은
이번 세션 범위 밖이라 건드리지 않음.

## chat 통합 검색 + grounding 설계
사용자가 "chat에서 검색할 때 DB와 wiki가 같이 검색되고, wiki 결과의 실제 데이터 기반은 DB가
되었으면 좋겠다"고 요구. 처음엔 "Wiki 쪽은 pg_trgm 키워드 검색 도구를 chat에 추가"안으로
답했으나, 이어서 사용자가 "wiki.js 내용을 청킹해서 DB에 벡터화 저장하는 건 어떠냐"고 제안 →
더 나은 방향이라 채택. 최종: Wiki.js 페이지를 마크다운 섹션 단위로 청킹해서 `wiki_chunks`
테이블(같은 PostgreSQL, pgvector)에 임베딩 저장. 아이템 페이지 경로가
`/dho/<category>/<item_id>`라서 청크에 category/item_id를 그대로 저장해두면, wiki 시맨틱
검색 결과 → DB 원본 레코드 조인이 바로 됨 (grounding 요구를 여기서 만족). item_id 없는
자유 위키 페이지(공략/개요 등)는 청크 텍스트 자체가 근거. 다만 짧은 키워드(1~2단어)는
임베딩 검색이 약할 수 있어 기존 `pg_trgm`/exact match 폴백은 그대로 유지하기로 함
(`FTS_MIN_LENGTH=3` 하이브리드 패턴과 동일한 이유).

**Why:** 위키 페이지는 DB에서 자동 생성되지만 이후 사람이 직접 편집(설명 보강, 가이드 추가
등)할 수 있어 DB만 검색해서는 그 편집 내용을 못 찾음. 그렇다고 wiki 텍스트만 근거로 답변하면
부정확할 수 있어(자유 서술이라 오탈자/오래된 정보 가능) DB로 되짚어 확인하는 grounding이
필요하다는 게 사용자 의도.

## notion-sync 완전 제거 결정
Postgres로 DB를 통합하면 `notion_pages`/`notion_fts`도 같이 옮기지 않는 한 chat이 더 이상
SQLite를 안 봐서 어차피 못 읽게 됨(그대로 두는 건 선택지가 아님) — 이 트레이드오프를
AskUserQuestion으로 확인한 결과 "완전히 제거(데코미션)"로 확정. NAS에서 실제로 돌고 있는
`dho-notion-sync` 컨테이너도 정지/제거 대상에 포함.

**Why:** 사용자가 "notion 관련 동기화 로직은 제외되어도 될 것 같다"고 먼저 언급 — Wiki.js가
생기면 개인 문서를 거기 직접 쓰면 되어 별도 노션 동기화가 불필요해진다고 판단한 것으로 보임.
Postgres 마이그레이션까지 굳이 해서 유지할 가치가 없다고 확인.

**How to apply:** Phase 1에서 `Dockerfile.notion-sync`/`sync_notion.py`/
`sync_notion_loop.sh`/`scratch_notion_sync.log` 삭제, docker-compose/deploy.sh/.env.example/
README/chat 도구 등록에서 관련 항목 전부 제거. `*-notion-sync.md`(보존된 이전 계획 문서)는
과거 기록이니 그대로 둔다(삭제 안 함).

## 파이프라인 스크립트 SQLite 잔류 범위 정정
`dho_webapp.py:123` `rebuild_derived_tables()`를 확인해보니, 항목 저장(`_save_item`)마다
`DERIVED_PIPELINE_SCRIPTS` 8개(`build_backlinks.py`/`build_acquisition.py`/
`materialize_generic.py`/`materialize_cannon.py`/`materialize_recipe.py`/
`materialize_consumable.py`/`materialize_tarotcard.py`/`build_search_index.py`)를
서브프로세스로 **동기적으로 즉시 재실행**해서 파생 테이블을 전체 재생성하고 있었음(전체
기준 로컬 약 12초). 이건 "가끔 도는 빌드 파이프라인"이 아니라 저장 시점 라이브 로직이라,
당초 계획("파이프라인 스크립트는 그대로 SQLite에 둔다")대로면 webapp이 Postgres에 써도
파생 테이블은 여전히 SQLite에만 갱신되어 chat/향후 wiki가 저장 직후 최신 데이터를 못 보는
문제가 생김.

**Why:** 사용자가 "백엔드 DB는 postgresql 하나로 통합"을 명시적으로 요구했으므로, 저장
시점에 즉시 재실행되는 이 8개는 Postgres 통합의 일부로 봐야 함. SQLite에 남겨도 되는 건
`dho_webapp.py`가 재실행하지 않는(=재크롤링 시에만 도는) `build_structured_db.py`/
`build_category_localization.py` 딱 2개뿐.

**How to apply:** `migrate_to_postgres.py`는 `items_core`/`raw_attrs`/`raw_tables`/
`category_localization` 등 "원본성" 테이블만 SQLite→Postgres로 옮기는 다리 역할만 하고,
파생 테이블은 옮기지 않는다 — 대신 위 8개 스크립트를 psycopg로 재작성해서 Postgres 위에서
직접 실행해 파생 테이블을 생성한다. `dho_webapp.py`의 `rebuild_derived_tables()`가 자식
프로세스에 넘기는 env도 `DHO_DB_PATH`(파일 경로) 대신 `DATABASE_URL`(접속 문자열)로 바뀜.

## Phase 1 구현 + 로컬 검증 완료 (2026-08-10)
docker-compose postgres 서비스 추가부터 notion-sync 제거, migrate_to_postgres.py, 8개 파생
스크립트 psycopg 재작성, chat/lib/dho-db.ts pg 재작성, dho_webapp.py psycopg 재작성까지 전부
구현 완료. 로컬 Docker(Docker Desktop 재기동 필요했음)로 postgres 컨테이너 띄워서
전체 파이프라인 실행 + webapp/chat 스모크 테스트 + 실제 챗봇 질문까지 end-to-end 검증함.

**발견/수정한 버그 2건** (SQLite는 관대하게 넘어갔지만 Postgres는 엄격해서 드러난 것들 —
[[dho-project-overview]]의 파이프라인이 SQLite 기준으로 오래 검증되어 있었던 만큼 이런 차이는
예상된 범위):
1. `materialize_generic.py`가 INTEGER 컬럼에 빈 문자열을 넣으려다 에러
   (`invalid input syntax for type integer: ""`) — SQLite 타입 어필리니티는 이걸 그냥 TEXT로
   저장해줬지만 Postgres는 안 됨. 빈 값은 NULL로 넣도록 수정.
2. `dho_webapp.py`의 `CAST(REPLACE(x, ",", "") AS INTEGER)`처럼 SQLite가 큰따옴표 문자열
   리터럴을 관대하게 봐주던 부분(원래는 식별자용) — Postgres에서 큰따옴표는 항상 식별자라
   그대로 두면 에러. 작은따옴표로 수정.
   같은 이유로 `chat/lib/dho-db.ts`의 `runSql`도 `SELECT * FROM (subquery)`에 별칭이
   없으면 Postgres에서 에러(SQLite는 별칭 없어도 허용) → `AS sub` 추가.

**성능 이슈 발견/수정**: `build_acquisition.py`가 개별 raw_tables 행마다 `INSERT`를
동기 실행하는 방식이라(수만 건) SQLite 로컬 파일 대비 Postgres 네트워크 왕복 오버헤드가
누적되어 120초 타임아웃을 넘김. psycopg의 pipeline 모드(`conn.pipeline()`, statement를
모아서 보내 왕복 횟수를 줄임)로 고쳐서 120초 초과 → 19.8초로 개선, `materialize_generic.py`도
같은 방식으로 43초로 개선. **다만 8개 스크립트 전체 실행 시간 합계는 대략 1~2분으로 원래
SQLite 기준 "~12초"보다 훨씬 느림** — `dho_webapp.py`의 `rebuild_derived_tables()`가 항목
저장마다 동기로 이걸 기다리는 기존 설계라, 항목 저장 시 사용자가 체감하는 응답 시간이
~12초에서 ~110초로 늘어남(실측). 타임아웃은 안 넘지만 UX 저하가 실재함.

**Why:** 사용자에게 아직 이 트레이드오프를 명시적으로 확인받지 않음 — 이번 세션에서는
"틀리지 않게 동작하는 것"을 우선했고, 추가 최적화(예: 저장 응답을 먼저 돌려주고 파생 테이블
재생성은 백그라운드로 돌리기, 또는 INSERT를 더 큰 배치/COPY로 묶기)는 범위 밖으로 미룸.

**How to apply:** 다음에 이 프로젝트를 다룰 때, 사용자가 "저장이 느리다"고 하면 이 항목부터
확인. 해결책 후보는 이미 위에 적어둠(비동기 백그라운드 재생성이 UX 개선 폭이 가장 큼).

## NAS 배포 완료 + 포트 충돌 발견 (2026-08-10)
`./deploy.sh` 실행 중 postgres 컨테이너가 호스트 포트 5432 바인딩에 실패
(`address already in use`). 원인은 NAS(UGREEN OS)가 이미 네이티브 PostgreSQL을
5432(시스템 자체 용도, `/usr/ugreen/etc/psql`)와 5433(video manager 앱,
`/volume1/@appstore/com.ugreen.videomgr/db`)에서 쓰고 있었던 것 — `docker ps`엔 안
보여서(컨테이너가 아니라 네이티브 프로세스) 처음엔 원인 파악에 시간이 걸림
(`ps aux | grep postgres`로 확인). 5434로 바꿔서 해결 — 컨테이너 내부 포트는 그대로
5432라 webapp/chat의 `DATABASE_URL`(내부 hostname `postgres:5432`)은 안 건드림, 호스트
포트 매핑만 변경. **로컬 docker-compose.yml도 같은 파일이라 5434로 같이 바뀜** — 이후
로컬에서 다시 테스트할 때 5432가 아니라 5434로 접속해야 함(로컬엔 원래 충돌이 없었지만
NAS와 같은 compose 파일을 쓰는 게 더 일관적이라고 판단, 굳이 환경별로 다르게 안 함).

**Why:** 사용자에게 확인받을 새도 없이 배포 도중 발견된 문제라 즉시 판단해서 처리함
(운영 중이던 webapp/chat이 재기동 과정에서 잠깐 내려간 상태였어서 빠른 복구가 우선).

**How to apply:** 이후 이 NAS에 다른 Docker 서비스로 Postgres를 또 띄울 일이 있으면
5432/5433은 항상 피할 것. `docker ps`에 없다고 포트가 비어있다고 단정하지 말고
`ss -tln`/`ps aux`로 네이티브 프로세스도 같이 확인할 것.

배포 자체는 `migrate_to_postgres.py`(로컬→NAS Postgres, LAN 직접 접속)로 원본 4개 테이블
이관 후, NAS에서 `docker compose exec webapp python <script>.py`로 파생 테이블 8개를
컨테이너 내부 네트워크(빠름)로 실행하는 순서로 완료. 기존 `dho-notion-sync`는
`docker compose up --remove-orphans`로 정지/제거됨. 최종 행 수 전부 로컬 검증과 일치,
webapp/chat/nginx-proxy 경유 HTTPS까지 전부 정상 확인.

## curl 셸 인코딩 문제 (검증 방법론 노트, 코드 버그 아님)
로컬 검증 중 Windows Git-Bash에서 `curl --data-urlencode`로 한글을 직접 넘기면 콘솔
코드페이지(cp949) 때문에 저장된 데이터가 깨졌다(예: "테스트대포"가 `%C5%BD%BA%C4...`처럼
저장됨). 처음엔 코드 버그로 의심했으나, Python `requests`/`urllib`로 문자열을 직접 만들어
보내니 정상 저장됨을 확인 — 순수 셸 인코딩 문제였음. **앞으로 이 프로젝트에서 한글 포함 요청을
셸(curl 등)로 테스트할 때는 Python으로 문자열을 만들어 보내는 방식을 쓸 것**, curl에 한글을
직접 인자로 넘기지 말 것.

## Phase 2 완료 — pgvector 아이템 시맨틱 검색 (2026-08-10)
`item_embeddings` 테이블(`build_embeddings.py`) + `chat`의 `semantic_search_items` 도구까지
구현/검증/NAS 배포 완료.

**embedded_text를 items_search.search_text로 재사용한 이유:** build_search_index.py가 이미
name+title+description+attrs를 통합한 텍스트(`items_search.search_text`)를 만들어두고 있어서,
임베딩용 텍스트를 따로 조합하는 로직을 또 만들지 않고 그대로 재사용함(중복 제거). 부작용:
`build_embeddings.py`는 `build_search_index.py`가 먼저 실행돼 있어야 함(파이프라인 순서
의존성 — 문서/스크립트 실행 순서에 이미 반영됨).

**임베딩 API 호출 방식**: `openai` pip 패키지 대신 `requests`로 REST 직접 호출 —
sync_notion.py가 notion-client 패키지 대신 requests를 직접 쓴 것과 같은 이유(불필요한
의존성 추가 안 함, 이 프로젝트의 기존 컨벤션과 맞춤).

**DERIVED_PIPELINE_SCRIPTS에 안 넣은 이유**: 이미 Phase 1에서 "8개 스크립트가 저장할 때마다
자동 재실행되어 저장 응답이 ~110초 걸린다"는 성능 문제를 발견했었는데
([[postgresql-마이그레이션-phase1]] 참고), 여기에 API 호출까지 추가되면 저장할 때마다
실제 비용이 발생하고 응답이 훨씬 더 느려짐 — `build_embeddings.py`는 의도적으로 자동
재실행 목록 밖에 두고 수동 실행 대상으로 분리함.

**품질 검증 방법**: 도메인 지식(게임 콘텐츠)이 없어서 임의의 개념 질문으로는 결과가
"맞는지" 판단하기 어려웠음 — 대신 이미 정답을 아는 항목(가나돌 사령부, 설명에 "생산 관련
연동을 위해 임시적으로 등록"이라고 적혀있음)을 완전히 다른 표현("제작 시스템과 연결하려고
임시로 만들어놓은 도시")으로 질의해서, 정답이 유사도 1위로 나오는지 확인하는 방식을 씀 —
실제로 1위(0.423)로 정확히 나와서 검증 성공. 이 "알고 있는 정답을 다르게 표현해서 질의"
방법은 도메인 지식 없이도 임베딩 검색 품질을 검증할 수 있는 재사용 가능한 패턴으로 기록해둠.

**Why:** 사용자가 Phase 1 완료 후 바로 "Phase2로 넘어가줘"로 진행 지시. 별도 확인 질문 없이
plan.md에 이미 있던 설계(OpenAI 임베딩, text-embedding-3-small 추정)대로 진행함 — 비용이
$0.20~0.30 수준으로 미미하고 임베딩은 언제든 재생성 가능해서 되돌리기 쉬운 결정이라 판단.

**How to apply:** Phase 3(Wiki.js)에서 위키 청크 임베딩을 만들 때 이 스크립트의 배치 호출/
재시도 로직을 거의 그대로 재사용할 수 있음(원래 plan.md에 그렇게 설계돼 있음).
