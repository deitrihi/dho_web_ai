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

## 2026-08-10 | Phase 3 착수 — Wiki.js 초기 설정 자동화

plan.md/checklist.md에 미리 설계는 돼 있었지만 세부 구현은 미착수 상태였음. 이 세션에서
Wiki.js 배포부터 chat 통합까지 전부 구현하고 로컬에서 종단간 검증까지 완료.

**Wiki.js 초기 설정(설치 마법사)이 예상보다 큰 난관이었음.** 웹 검색 결과 "official
`ghcr.io/requarks/wiki` 이미지가 `ADMIN_EMAIL`/`ADMIN_PASS` 환경변수로 마법사를
스킵한다"는 정보가 나왔는데, 실제로 컨테이너를 띄워보니 전혀 적용되지 않고 "Switching to
Setup mode"로 항상 브라우저 접속을 요구함 — 검색 결과가 가리킨 건 별도 서드파티 포크
얘기였던 것으로 보임(정보 출처를 그대로 믿지 않고 실제로 띄워서 검증한 게 맞았음). 이
프로젝트엔 브라우저/Playwright 등 GUI 자동화 도구가 없어서 그대로면 막힐 뻔했는데,
`gh api`로 requarks/wiki 리포의 `server/setup.js` 소스를 직접 읽어서 마법사가 실제로 하는
일이 `POST /finalize`(JSON body: adminEmail/adminPassword/siteUrl/telemetry) 요청 하나뿐임을
확인 → curl/Python으로 그대로 재현해서 완전 자동화(브라우저 불필요)에 성공.

**Why:** 브라우저 자동화 도구가 없는 환경에서 33,496개 페이지를 만들려면 최소한 최초
설치 과정부터 스크립트로 재현 가능해야 함. 소스 코드를 직접 읽는 게 검색 결과보다
신뢰할 수 있는 근거였음.

**How to apply:** NAS 배포 시에도 컨테이너를 처음 띄운 뒤 동일한 `POST /finalize` 호출이
필요함(deploy.sh나 별도 초기화 스크립트에 반영 필요, 체크리스트 미완료 항목).
[[dho-project-overview]]

## 2026-08-10 | GraphQL 인코딩 버그로 오인했던 사례 — 실제로는 Git Bash 콘솔 표시 문제

curl로 한글이 포함된 GraphQL mutation을 보내고 `psql`로 결과를 확인했더니 제목이
"���Ϸ� �׽�Ʈ" 처럼 깨져 보여서 인코딩 버그(curl이 한글을 깨뜨렸다)로 판단하고 페이지를
삭제 후 Python으로 재시도했는데, Python으로 만든 것도 똑같이 깨져 보였음. `encode(title::
bytea, 'hex')`로 원시 바이트를 직접 대조해보니 실제로는 완전히 정상적인 UTF-8이었음
(`ed8c8c...` = "파일럿 테스트") — 즉 DB엔 아무 문제가 없었고, Git Bash 콘솔이 UTF-8을
표시하는 방식(코드페이지)의 문제였을 뿐이었음.

**Why:** memory에 "이 환경에서 curl에 한글 직접 넘기면 깨짐, Python으로 테스트할 것"이라는
기존 기록이 있어서 처음엔 그 패턴이라고 확신하고 넘어갈 뻔했는데, hex로 실제 바이트를
대조하는 한 단계를 더 거치니 진짜 원인(터미널 표시)이 달랐음을 알게 됨.

**How to apply:** 앞으로 이 환경에서 한글 데이터가 터미널에 깨져 보이면, 그게 실제 데이터
손상인지 터미널 표시 문제인지 `encode(col::bytea,'hex')` 같은 방법으로 먼저 구분할 것 —
Python 사용 여부와 무관하게 콘솔 표시는 깨질 수 있음. 파일로 써서 Read 툴로 읽으면
표시 문제 없이 정확히 확인 가능(이번에 사용한 방법).

## 2026-08-10 | Wiki.js 웹훅 미지원 확정 → 폴링 방식으로 결정

plan.md 리스크 항목("Wiki.js가 페이지 저장 시점 이벤트를 웹훅으로 제공하는지 미확인")을
웹 검색으로 확인 — 2026-08 기준 requarks/wiki 이슈 트래커에 "Webhooks" 기능 요청이
여전히 미구현 상태로 남아있음(서드파티 npm 패키지로 우회하는 사례만 있음, 공식 지원
아님). 이에 따라 `build_wiki_chunks.py`를 폴링 방식으로 설계 확정 — `wikidb.pages.hash`
(Wiki.js가 저장할 때마다 자체적으로 갱신하는 콘텐츠 해시 컬럼)를 매 실행마다 비교해서
바뀐 페이지만 재청킹. 별도 해시 계산 없이 Wiki.js가 이미 관리하는 컬럼을 그대로 재사용.

**Why:** 웹훅이 없으니 "저장 즉시 반영"은 불가능하고, 주기적 재실행(cron 등)으로 근사할
수밖에 없음 — 반영 지연이 있다는 걸 사용자에게 명확히 해야 함.

**How to apply:** NAS 배포 시 `build_wiki_chunks.py`를 cron으로 주기 실행하도록 등록
필요(체크리스트 미완료 항목). 실행 주기는 아직 미정 — 사용자와 상의 필요(너무 자주
돌리면 OpenAI 임베딩 API 비용/빈도가 늘고, 너무 뜸하면 위키 편집이 검색에 늦게 반영됨).

## 2026-08-10 | wiki_chunks 청킹 설계 — 헤더 기준 분할 + 제목 접두어 임베딩

`build_wikijs_pages.py`가 만드는 문서 구조("# 제목" + "## 속성" + "### <표 이름>" 반복)에
맞춰 정규식(`^#{1,3} .+$`)으로 헤더 라인마다 새 청크를 시작하는 방식을 채택. 표 하나당
청크 하나(예: "획득 아이템", "판매 아이템")가 되어 "이 던전에서 뭘 얻을 수 있어?" 같은
질문에 적당한 크기의 근거를 반환할 수 있음. 임베딩 입력(embedded_text)에는 청크 본문
앞에 페이지 제목을 붙여서("{title}\n\n{chunk}") 문맥을 보강함 — item_embeddings의
embedded_text 패턴과 동일한 이유(짧은 표 청크만 단독으로 임베딩하면 "이게 무슨 항목의
표인지" 정보가 없어서 검색 품질이 떨어짐).

**Why:** 사람이 자유 위키 페이지(공략/개요 글)를 쓸 때도 동일한 헤더 규칙만 지키면 같은
청킹 로직이 그대로 적용되므로, 자동 생성 페이지와 수동 페이지를 구분 처리할 필요가 없음.

**How to apply:** 청킹 결과가 너무 크거나 작다고 판단되면(예: "## 속성"이 항목이 많은
카테고리에서 지나치게 길어짐) MAX_TEXT_CHARS(6000자) 절단 외에 추가 분할 로직이 필요할 수
있음 — 아직 발생 안 했지만 전체 70개 카테고리 확대 후 재확인 필요.

## 2026-08-10 | 전체 70개 카테고리 확대 — Windows 백그라운드 프로세스 추적 이슈

`build_wikijs_pages.py --all`을 백그라운드로 돌리려다 Windows에서 `os.execve`/
`subprocess.Popen`(부모가 곧바로 종료)를 쓰면 하네스가 추적하는 PID가 실제 작업
프로세스와 分리되어, 실제로는 계속 일하고 있는데도 "completed"로 잘못 보고되는 상황을
겪음(DB를 직접 폴링해서 실제로는 계속 진행 중임을 확인). 처리량 실측 약 25~30페이지/분.

**Why:** Windows는 POSIX fork/exec와 동작이 달라서, 백그라운드로 띄운 파이썬 스크립트가
그 안에서 다시 서브프로세스를 실행하면 하네스의 완료 알림을 신뢰할 수 없음.

**How to apply:** 앞으로 이 환경에서 오래 걸리는 스크립트를 백그라운드 실행할 땐, 완료
알림에 의존하지 말고 DB/로그 파일을 직접 폴링해서 실제 진행 상황을 확인할 것. 가능하면
래퍼 스크립트 없이 대상 스크립트를 직접 background 실행하는 게 더 안전함.

## 2026-08-11 | Wiki.js 동시 쓰기 버그 + chat 도구 중복 호출 버그 (사용자 스크린샷으로 발견)

**Wiki.js 동시 쓰기 버그**: `build_wikijs_pages.py --all --concurrency 12`로 전체 백필을
돌리던 중 cannon 566건 중 75건, certificate 70건 중 42건이 실패. 로그를 보니 인코딩
문제가 아니라 Wiki.js 2.5.314가 페이지 생성 시 내부적으로 도는 "rebuild-tree" 작업이
동시 요청을 못 견디고 `pageTree_pkey`/`pagetree_parent_foreign` 위반으로 깨지는 서버
자체 버그였음. 마크다운 생성(DB 조회, CPU 작업)은 스레드풀로 계속 병렬 처리하되, 실제
Wiki.js에 쓰는 create/update 호출만 전역 락(`_write_lock`)으로 직렬화해서 해결 —
cannon/certificate 재실행 결과 실패 0건으로 확인.

**chat 도구 중복 호출 버그**: 사용자가 "플레이트 아머 재료+구매처" 질문 스크린샷을 공유 —
모델이 강철/철재/모피 각각에 대해 `get_item_detail`을 부른 뒤 `search_items`로 같은
키워드를 또 조회해서(얻는 정보가 겹치지 않는데도) 호출 수만 두 배로 쓰다가
`stepCountIs(16)` 한도에 걸려 답을 못 끝냄. 시스템 프롬프트에 "같은 키워드로 도구
중복 호출 금지" 규칙을 명시하고(get_item_detail의 획득_방법 필드에 구매처 정보가 이미
있다는 점 재강조), `search_items` 도구 설명에도 동일 경고를 추가, `stepCountIs`를
16→24로 상향. 동일 질문 재현 시 도구 호출 10회+ 실패 → 4회(재료당 get_item_detail 1번씩)
정상 완료로 검증됨.

**Why:** 두 버그 다 겉보기엔 "AI가 이상하게 답한다"로만 보이는데, 실제로는 하나는
Wiki.js 서버 동시성 버그, 하나는 프롬프트가 도구 사용을 충분히 제약하지 않은 문제라
원인이 서로 다름 — 로그/실제 호출 내역을 까보지 않고 추측으로 고쳤으면 엉뚱한 곳을
건드릴 뻔했음.

**How to apply:** Wiki.js 관련 스크립트에서 페이지 생성/수정을 병렬화할 땐 항상 실제
쓰기 호출은 직렬화할 것(이 버전의 서버 한계). chat에 새 도구를 추가할 때는 기존 도구와
정보가 겹치는 부분이 있는지 확인하고, 겹치면 시스템 프롬프트에 "어느 도구를 우선
쓰고 다른 건 부르지 말라"를 명시적으로 적어둘 것 — 도구 설명만으로는 모델이 중복
호출을 피하지 못하는 경우가 있음.

## 2026-08-11 | NAS Wiki.js 인프라 설치 완료 (데이터는 아직 없음) + 반영 방식 결정

로컬 백필(70개 카테고리)이 진행되는 동안 NAS 쪽 Wiki.js 인프라를 먼저 설치함(로컬 백필과
NAS 인프라 설치는 서로 독립적이라 병행 가능하다고 판단). `./deploy.sh`(인자 없이 전체
서비스)로 코드 배포 → `wikidb` 수동 생성(기존 postgres_data 볼륨이라 init.sql 재실행
안 됨, 로컬과 동일 패턴) → `POST /finalize`로 브라우저 없이 설치 마법사 완료(로컬에서
검증한 방법 그대로 재사용) → GraphQL 로그인 검증까지 완료. NAS postgres는 재생성됐지만
볼륨 덕분에 기존 33,496건 데이터는 그대로 유지됨.

배포 전 NAS `.env`를 먼저 확인했는데 로컬과 값이 동일해서(WIKI_* 신규 변수만 추가되는
상황) `deploy.sh`가 `.env`를 그대로 덮어써도 안전하다고 판단하고 진행함 — `deploy.sh`의
`EXCLUDE_PATTERNS`에 `.env`가 빠져있어서 항상 로컬 `.env`로 NAS `.env`를 덮어쓴다는 점은
주의(내용이 다르면 위험할 수 있음, 이번엔 동일해서 문제 없었음).

**NAS에 실제 페이지 데이터를 채우는 방법 결정**: 로컬에서 이미 검증된(직렬화 버그 수정
포함) `wikidb`를 `pg_dump`/`restore`로 그대로 NAS에 복사하는 방식을 사용자가 선택함
(대안이었던 "NAS에서 build_wikijs_pages.py --all 재실행"은 시간이 두 배로 들고
wiki_chunks 임베딩까지 다시 만들면 OpenAI 비용도 두 번 나가서 비효율적).

**Why:** 로컬 백필을 다시 반복하지 않고 검증된 결과물을 그대로 옮기는 게 시간/비용
양쪽에서 유리함.

**How to apply:** 로컬 백필 + `build_wiki_chunks.py --all` 전체 완료 후,
1) 로컬 `wikidb` 전체를 `pg_dump`로 덤프해서 NAS `wikidb`에 restore
2) 로컬 `dho` DB의 `wiki_chunks`/`wiki_page_state`/`wiki_chunk_sync_state` 테이블도
   같은 방식으로 NAS `dho` DB에 복사(임베딩 재생성 비용 절감)
3) NAS `chat`이 이미 `semantic_search_wiki` 도구를 갖고 있으므로 재배포 불필요, 데이터만
   들어오면 바로 동작할 것으로 예상 — 복사 후 실제 질문으로 재검증 필요.

## 2026-08-15 | Phase 3 최종 완료 — 전체 백필/청크/NAS 이관 마무리

전체 70개 카테고리(33,496건) 백필과 125,328개 청크 임베딩을 로컬에서 전부 마치고,
NAS로 데이터를 이관해서 실사용 검증까지 끝냄. 진행 중 만난 문제들과 해결.

1. **Wiki.js 페이지 누적에 따른 저장 지연**: 백필 후반부(skill 카테고리 등)에서 저장
   요청이 기본 30초 타임아웃을 넘기는 사례가 급증(487건 중 322건 실패). `docker stats`로
   확인해보니 Wiki.js 컨테이너가 CPU 111%로 거의 풀로 돌고 있었음 — 페이지가 3만 개
   넘게 쌓이면서 저장마다 하는 검색 인덱싱/페이지트리 갱신 비용이 누적된 것으로 보임.
   `REQUEST_TIMEOUT`을 하드코딩에서 `WIKIJS_REQUEST_TIMEOUT` 환경변수로 바꾸고, 실패한
   413건만 골라서 90초 타임아웃으로 재시도 → 전부 성공.
2. **로컬 Docker Desktop이 백필 도중 다운**: `com.docker.service`가 멈춰서 postgres
   연결이 끊기며 스크립트가 `psycopg.OperationalError`로 죽음. `Start-Process 'Docker
   Desktop.exe'`로 재기동 후 `until docker info; do sleep 5; done` 폴링으로 복구 확인.
   `restart: unless-stopped` 정책 덕분에 전 컨테이너가 자동 복구됐고, 볼륨 덕분에
   데이터 손실도 없었음 — idempotent 설계(콘텐츠 해시 비교) 덕분에 그냥 재실행만으로
   이어감.
3. **NAS 데이터 이관**: 재백필 대신 로컬에서 이미 검증된 DB를 그대로 옮기기로 한 결정
   (사용자 선택)대로 `pg_dump -Fc`(custom format) → `scp` → `pg_restore --clean
   --if-exists` 순서로 진행. `wikidb`는 28MB, `wiki_chunks` 등 3테이블은 859MB(벡터
   데이터가 대부분). NAS의 최신 SSH가 SFTP 기반 `scp`에서 "No such file or directory"로
   실패해서(이 NAS의 기존에 알려진 rsync 이슈와 같은 계열 문제로 추정) `scp -O`(레거시
   SCP 프로토콜)로 우회. `pg_restore`가 종료코드 1(경고성 메시지 때문)을 반환해서 "실패"
   알림이 왔지만, 실제로는 건수(125,328/33,496)와 HNSW 인덱스까지 전부 정상 복원된 것을
   확인 — **pg_restore의 비영(non-zero) 종료코드는 항상 실제 실패 여부를 직접 데이터로
   재확인해야 함, 종료코드만 보고 판단하면 안 됨**.

**Why:** 셋 다 "AI가 이상하게 동작한다"가 아니라 인프라/운영 이슈였음 — 실제 데이터
상태를 직접 조회해서 진위를 확인하는 습관이 오탐(false alarm)에 낚이지 않는 데 계속
도움이 됐음(이번 세션에서 반복된 패턴).

**How to apply:** 앞으로 Wiki.js에 대량 쓰기 작업을 할 때는 페이지 수가 늘어날수록
느려진다는 걸 감안해서 타임아웃을 넉넉히 잡을 것. `pg_restore`/`pg_dump` 계열 명령은
종료코드가 아니라 실제 테이블 건수로 성공 여부를 판단할 것. 로컬 장시간 백그라운드
작업은 Docker Desktop이 죽을 수 있다는 걸 전제로 idempotent하게 설계해두는 게
(이번처럼) 결국 도움이 됨.

## 2026-08-15 | 항목 페이지 사용자 편집 보존 마커 추가

Phase 3 완료 후 사용자가 "items_core를 갱신하면 사람이 Wiki.js에 추가한 내용도
사라지느냐"고 질문 — 실제로 그랬음(`build_wikijs_pages.py`의 `pages.update`가 페이지
전체를 통째로 교체하는 방식이라, `dho/<category>/<item_id>` 페이지에 사람이 직접 추가한
내용이 다음 DB 갱신 때 같이 덮어써짐). 사용자가 "자동 생성/수동 추가 영역을 명확히
분리"하는 방식을 선택.

**구현**: `<!-- dho:user-content -->` HTML 주석을 마커로 채택(마크다운 렌더링 시
화면에 안 보임). `upsert_page()`가 갱신(update) 전에 기존 페이지 콘텐츠를 먼저
조회(`SINGLE_BY_PATH`에 `content` 필드 추가)해서 이 마커 이후 텍스트를 찾으면
(`extract_user_content()`), 새로 생성한 DB 기반 콘텐츠 뒤에 그대로 이어붙인다 — 마커
앞부분(자동 생성 영역)만 항상 DB 기준으로 교체되고, 마커 뒷부분(사용자 추가 영역)은
손대지 않고 보존됨. 신규 생성(create) 시에는 보존할 기존 내용이 없으므로 그대로 진행.

**검증**: tarotCard/8611 페이지로 실제 테스트 — GraphQL로 마커+텍스트를 수동 추가 →
`wiki_page_state`에서 해당 항목 삭제(강제 재동기화 유발) → `build_wikijs_pages.py`
재실행 → 속성/표는 최신 상태로 갱신되면서 마커 이후 사용자 텍스트는 정확히 1회만
보존됨 확인. (테스트 중 Wiki.js의 `pages.update`가 `tags` 파라미터 없이 호출하면
"Cannot read properties of undefined (reading 'map')"로 실패하면서도 content는 이미
저장해버리는 서버 버그를 발견 — 항상 description/tags/title을 전부 채워서 호출해야
함, 이 프로젝트 스크립트는 이미 그렇게 하고 있어서 영향 없음.)

**Why:** 항목 상세 페이지 안에 사람이 보충 설명을 addendum처럼 추가하고 싶어할 수
있는데, DB 동기화 때마다 사라지면 그 기능을 못 씀 — 자동/수동 영역을 코드 레벨에서
분리해야 안전하게 공존 가능.

**How to apply:** 사용자에게 안내할 때는 "항목 페이지에 내용을 추가하려면 페이지
맨 아래 `<!-- dho:user-content -->` 줄을 넣고 그 아래에 원하는 내용을 쓰면 된다"고
설명. 이 마커가 없는 페이지는 기존과 동일하게(보존 로직 없이) 전체 교체됨. NAS에는
아직 이 코드 변경이 배포 안 됨 — 다음 NAS 배포 시 반영 필요(지금 당장 급한 건 아님,
NAS에서 아직 아무도 위키를 수동 편집한 적 없음).

## 2026-08-15 | Phase 4 착수 — 위키 브라우징 진입점 없음 발견 + 인덱스/Navigation 구현

사용자가 "wiki 문서들은 만들어졌는데 그냥 조회시(홈 화면/사이드바) 아무것도 안 나온다"고
보고. 원인 확인: `build_wikijs_pages.py`가 `dho/<category>/<item_id>` 낱개 페이지만
생성하고, 이를 연결하는 상위 인덱스 페이지나 Wiki.js Navigation 메뉴는 만든 적이
없었음(질문으로 "홈 화면/사이드바가 비어 보이는 상황"인지 먼저 확인해서 검색창/관리자
페이지 목록 문제가 아님을 확정한 뒤 진행).

**추가 요구사항**: 사용자가 `webapp`엔 못 넣는 자유 형식 글(게임 팁/공략)을 위키에 직접
쓰고 싶고, 이것도 chat 검색에 반영되길 원함. `build_wiki_chunks.py`를 다시 확인해보니
`wikidb.pages` 전체를 경로 제한 없이 읽어서(`dho/` 접두어 필터 없음) 청킹·임베딩하고
있었음 — **이미 지원되는 기능이라 추가 구현 불필요**, `page_path`가
`dho/<category>/<item_id>` 패턴이 아니면 `PAGE_PATH_RE` 매치가 안 돼 category/item_id가
그냥 NULL로 저장되고, `chat/lib/dho-db.ts`의 `semanticSearchWiki()`도 이미 이 케이스를
처리하고 있었음(코드 읽고 확인, 재작성 안 함).

**구현 (`build_wikijs_pages.py`)**:
- `build_root_index_markdown()` — `category_localization`(group_title_ko/group_order/
  order_in_group)을 그대로 재사용해 대분류별 카테고리 목록 + 항목 수를 만들고 `dho`
  경로에 저장. `dho_webapp.py` 홈 화면과 같은 그룹핑 소스라 두 화면의 분류 체계가
  자연히 일치함.
- `build_category_index_markdown()` — 카테고리 안 전체 항목 링크 목록, `dho/<category>`
  경로에 저장. 항목이 최대 5,052건(quest)인 카테고리도 있어 페이지가 커지지만, 이미
  상세 페이지도 큰 표를 렌더링하고 있어 Wiki.js가 다루는 데 문제없다고 판단 —
  페이지네이션 등 추가 구조 없이 flat list로 단순하게 구현(과설계 방지).
- `guides` stub 페이지 — 자유 문서를 쓸 앵커. 사용자가 `guides/<하위경로>`에 문서를
  만들면 됨.
- 셋 다 기존 `upsert_page()`를 그대로 재사용 — 사용자가 마커(`<!-- dho:user-content -->`)를
  추가하면 재실행해도 보존되는 동작이 인덱스/guides 페이지에도 동일하게 적용됨(추가
  구현 없이 기존 메커니즘 재사용).
- 인덱스 페이지는 콘텐츠 해시 스킵 로직(`wiki_page_state`) 없이 매 실행마다 무조건
  upsert — 최대 71개 페이지뿐이라 33,496개 항목처럼 스킵 최적화가 필요할 정도로
  비싸지 않다고 판단, 새 상태 테이블을 만드는 대신 단순하게 감.

**Navigation 자동 등록**: Wiki.js GraphQL 스키마를 introspection으로 직접 조사해서
`navigation.tree`(조회)/`navigation.updateTree`(갱신)가 존재하는 걸 확인 — Admin UI에서
수동으로 설정해야 하는 줄 알았는데 API로 가능했음. `updateTree`는 해당 locale의 트리
전체를 통째로 교체하는 방식이라, 먼저 `tree` 쿼리로 기존 항목(id 목록)을 읽고 우리
항목("dho-home", "dho-guides")이 없을 때만 추가해서 다시 쓰는 멱등 로직으로 구현 —
기존 "Home" 항목이나 사용자가 나중에 Admin에서 수동 추가한 항목을 덮어쓰지 않음.

**검증**: 로컬 Wiki.js에서 `--categories tarotCard` 파일럿 실행 → GraphQL/DB 직접 조회로
`dho`/`dho/tarotCard`/`guides` 콘텐츠 확인 + `navigation.tree`에 항목 2개 추가된 것 확인
+ 실제 HTTP GET(`/en/dho`, `/en/dho/tarotCard`, `/en/guides`, `/en/dho/tarotCard/8611`)
전부 200 확인. 이어서 `--all`로 나머지 69개 카테고리 인덱스 페이지 백필(기존 33,496개
항목은 해시 동일이라 전부 스킵, Wiki.js 쓰기는 카테고리 인덱스 69건 + 루트 1건뿐이라
가벼움).

**부수 발견 → 수정 완료(2026-08-15 후속)**: `main()` 마지막 요약 print문의 "—"(em dash,
U+2014)가 Windows 콘솔 기본 코드페이지(cp949)로 인코딩이 안 돼 `UnicodeEncodeError`로
스크립트가 막판에 죽는 걸 발견 — 이번 세션에서 새로 만든 버그 아니라 기존 코드에 원래
있던 문제(다른 print문들은 em dash가 없어서 안 걸림). 실제 데이터 쓰기는 이 print 전에
이미 다 끝나서 기능상 영향은 없었지만, 사용자 요청으로 수정. `sys.stdout.reconfigure
(encoding="utf-8")`/`sys.stderr.reconfigure(...)`를 import 직후에 추가해서 콘솔 코드페이지와
무관하게 항상 UTF-8로 출력하도록 함 — `PYTHONIOENCODING=utf-8`을 매번 환경변수로 넘겨줄
필요 없어짐. `--categories tarotCard`로 재실행해서 마지막 요약 줄까지 정상 출력되고
exit code 0인 것 확인.

**Why:** Navigation을 API로 등록하면 "관리자가 수동으로 Admin 페이지 들어가서 설정"
단계 없이 스크립트 재실행만으로 완결됨 — NAS 배포 때도 동일 스크립트 실행으로 충분.

**How to apply:** NAS에도 이 스크립트를 재실행하면 인덱스/guides/Navigation이 동일하게
반영됨(로컬처럼 처음부터 다시 백필할 필요 없음 — `wiki_page_state`가 이미 NAS에도
복원돼 있어서 항목 쓰기는 전부 스킵되고 인덱스/Navigation만 새로 생김). 자유 위키
문서(가이드/팁)는 `guides/` 아래 아무 경로에나 만들면 되고, 다음 `build_wiki_chunks.py`
실행(폴링) 때 자동으로 청킹·임베딩됨 — 별도 등록 절차 없음.

## 2026-08-16 | NAS Wiki.js `/dho` 404 — 원인은 namespacing이 아니라 locale 불일치

NAS Phase 4 반영(`build_wikijs_pages.py --all`) 후에도 `/dho`가 계속 404. 처음엔 Wiki.js
Localization "namespacing"(URL에 locale 접두어 강제)이 켜져 있는 걸 의심해서 끄는
진단 스크립트(`fix_wikijs_localization.py`)를 만들어 돌렸는데, 실행해보니 NAS는 이미
namespacing이 꺼져있었고(`locale:"ko", namespacing:false`) 원인이 아니었음.

실제 원인: `build_wikijs_pages.py`가 페이지를 만들 때 `locale:"en"`으로 하드코딩돼있는데,
NAS Wiki.js 사이트 기본 locale은 `ko`. namespacing이 꺼진 상태에서 접두어 없는 경로는
사이트 기본 locale로 조회되므로 `(path="dho", locale="ko")`를 찾지만 실제 페이지는
`locale="en"`이라 못 찾음 — `/en/dho`처럼 명시적으로 locale을 지정해야만 일치해서 200이
나왔던 것. 로컬은 사이트 기본 locale이 이미 `en`이라 우연히 접두어 없이도 동작했던 것뿐.

**결정**: 사이트 locale을 en으로 바꾸는 대신, 페이지 locale을 ko로 마이그레이션(사용자 선택
— 콘텐츠가 전부 한국어라 의미상 ko가 맞음). GraphQL `localization.downloadLocale`/
`updateLocale` 실제 mutation 이름을 introspection으로 확인(처음 추측한
`updateLocalization`은 존재하지 않았음). 로컬 wikidb에서 먼저 전체 절차 검증 후 동일하게
NAS에 적용.

**적용 내용**:
1. `build_wikijs_pages.py` 3곳(`CREATE_PAGE`의 `locale:"en"`, `find_existing_page`의 locale
   파라미터, `NAV_LOCALE`)을 `ko`로 수정
2. 로컬: `localization.downloadLocale(locale:"ko")`로 ko 언어팩 설치 → `updateLocale`로 사이트
   기본 locale을 en→ko로 변경
3. 로컬+NAS 공통: `pages`/`pageTree`/`pageHistory`/`pageLinks`.`localeCode` en→ko 일괄
   UPDATE(트랜잭션), `navigation` 설정 JSON의 `"locale":"en"`→`"ko"` 치환
4. `users.localeCode`(계정 UI 언어 설정)는 콘텐츠 locale과 무관한 별개 값이라 그대로 둠
5. 로컬/NAS 양쪽 `/dho`, `/dho/tarotCard/8611`, `/guides` 전부 200 확인 후 수정된
   `build_wikijs_pages.py`를 NAS로 재전송, 진단용 스크립트는 삭제

**Why:** DHO 콘텐츠가 전부 한국어인데 locale이 en으로 태깅돼있던 게 애초에 잘못이었고,
site locale(ko)이 이미 NAS 기준이었으므로 페이지 쪽을 맞추는 게 데이터 의미상 더 맞고
사이트 설정 변경(en으로) 대비 두 환경(로컬/NAS)을 장기적으로 일관되게 만드는 방향.

**How to apply:** 앞으로 `build_wikijs_pages.py`를 재실행하면 자동으로 `ko` locale로
생성/조회하니 추가 조치 불필요. Wiki.js GraphQL mutation 이름을 추측하지 말고
`__type(name:"...")` introspection으로 먼저 확인할 것(이번에 `updateLocalization`이라고
추측했다가 틀렸음).

## 2026-08-16 | Wiki.js 홈페이지("/") 리다이렉트 — scriptJs 활용

"/"가 계속 "Welcome to your wiki" 초기 화면을 보여주는 문제 해결 요청. GraphQL
`__schema` 전체를 introspection으로 뒤져 `home`/`landing`/`redirect` 관련 필드를 찾아봤지만
`SiteConfig`에 홈페이지 경로를 지정하는 설정 자체가 없음을 확인. Wiki.js 라우팅은 그냥
`path=""`(빈 문자열) 페이지가 있으면 그게 "/"로 서빙되는 구조라, 실제 리다이렉트를 하려면
그 페이지 콘텐츠 안에서 직접 이동시켜야 함.

`pages.create`/`update` mutation 인자에 `scriptJs`/`scriptCss`(페이지별 커스텀 스크립트,
공식 지원 기능)가 있는 걸 introspection으로 발견 → `path=""` 페이지를 만들고
`scriptJs: "window.location.replace('/dho');"`로 설정. DB 확인 결과 `pages.extra` JSON
컬럼(`{"js":"...","css":""}`)에 저장됨. JS 비활성 환경 대비 페이지 본문에도 `/dho` 링크를
같이 넣어둠(마크다운 콘텐츠라 진짜 fallback).

**Why:** Wiki.js에 사이트 차원의 "홈페이지 지정" 설정이 없어서, 리버스 프록시 레벨
리다이렉트(이 프로젝트 docker-compose엔 프록시가 없음) 아니면 페이지 콘텐츠 레벨 트릭 둘
중 하나가 필요했는데, 후자가 인프라 변경 없이 Wiki.js API만으로 끝나서 더 간단함.

**How to apply:** `create_home_redirect.py`는 idempotent(기존 루트 페이지 있으면
scriptJs만 갱신)라 재실행 안전. curl로는 JS 실행 여부를 확인할 수 없음(Wiki.js가 SSR 없이
클라이언트에서 렌더링 — 초기 HTML엔 스크립트가 안 보이고 Vue가 마운트된 후 실행됨) —
실제 브라우저로 "/" 접속해서 `/dho`로 넘어가는지 최종 확인 필요, 사용자에게 요청함.

## 2026-08-16 | 홈페이지 리다이렉트 후속 수정 — path=""가 아니라 path="home"이어야 함

위 항목(`scriptJs`로 리다이렉트)을 실제 배포했는데도 "/"가 계속 welcome 화면을 보여줌.
`curl http://localhost:3001/`로 받은 원본 HTML을 직접 까보니 `<welcome locale="ko">` 컴포넌트가
그대로 박혀있었음(우리 페이지 콘텐츠가 아예 안 쓰임). Wiki.js는 서버 렌더링 없이 SPA
셸만 내려주고 라우팅을 서버 컨트롤러가 결정하는 구조라, 이 마크업 자체가 "서버가 어떤 뷰를
선택했는지"를 보여주는 확실한 증거였음.

`gh api repos/requarks/wiki/contents/server/controllers/common.js`와
`server/helpers/page.js`를 직접 읽어서 원인 확정. `parsePath()`가 `if (rawPath === '')
{ rawPath = 'home' }`로 루트 요청을 항상 `path: 'home'`으로 정규화한 뒤 그 경로로 페이지를
조회함 — `path=""`으로 만든 페이지는 이 흐름에서 절대 매치될 일이 없는 경로였음(요청이
`""`으로 들어오는 경우 자체가 없음). `pages.move(id, destinationPath:"home", ...)`로
옮기자 즉시 `<page path="home" ...>`로 정상 렌더링 확인.

**Why:** curl 200 응답만 보고 "우리 페이지가 서빙되고 있다"고 판단했던 게 성급했음 — Wiki.js는
`/robots.txt`, 정적 자산, 존재하지 않는 경로(404) 등을 빼면 사실상 모든 경로에 같은 SPA
셸을 200으로 내려주므로, 실제로 어떤 컴포넌트/데이터가 렌더링되는지는 HTML 안의 커스텀
엘리먼트 태그(`<page ...>` vs `<welcome ...>`)를 봐야 확인 가능했음.

**How to apply:** Wiki.js 라우팅 관련 문제는 GraphQL introspection만으로는 못 잡음(이건
프론트/서버 라우팅 로직이라 스키마에 안 드러남) — 이번처럼 `gh api`로 requarks/wiki 소스를
직접 읽는 게 빠름. 응답 코드(200/404)만으로 "제대로 렌더링됐다"고 단정하지 말고, HTML 안의
실제 마크업(어떤 Vue 컴포넌트가 박혔는지)까지 확인할 것.

## 2026-08-16 | 홈페이지를 리다이렉트 대신 정적 2-링크 페이지로, 사이드바는 홈에서만 숨김

사용자가 리다이렉트 방식이 "이상하다"고 판단해서, `home` 페이지 자체를 최종 콘텐츠(DHO
아카이브/가이드 링크 2개)로 직접 채우는 쪽으로 방향 전환. NAS는 사용자가 Admin 편집기로
이미 콘텐츠를 2-링크로 교체해뒀었지만 `scriptJs`(구 리다이렉트)가 그대로 남아있어서 실제
브라우저에서는 여전히 `/dho`로 튕겨나갈 수 있는 상태였음 — 로컬도 같은 콘텐츠로 맞추고
양쪽 다 `scriptJs`를 빈 문자열로 초기화.

**좌측 Navigation 사이드바를 홈에서만 숨기는 문제**: `gh api`로 Wiki.js 프론트엔드 소스
(`client/themes/default/components/page.vue`, `server/views/page.pug`)를 직접 읽어서
확인한 결과, 사이드바는 `navMode !== 'NONE'` 조건으로만 켜지고 `navMode`는
`navigation.updateConfig(mode:...)`로 설정하는 **사이트 전체** 값 — 페이지별로 켜고 끄는
공식 옵션이 없음. `path === 'home'`일 때 breadcrumb 툴바만 숨기는 예외 코드는 있었지만
사이드바 자체엔 예외가 없었음. AskUserQuestion으로 "홈만" vs "위키 전체" 확인 → "홈만" 선택.

해결책으로 `scriptCss`(페이지별 커스텀 CSS, 공식 지원)에
`.v-navigation-drawer{display:none!important}` + `.v-main{padding-left:0!important}` 적용
— 후자는 Vuetify가 드로어 폭만큼 본문에 남겨두는 padding을 보정하기 위함(Vuetify JS가
inline style로 계산해서 넣는 값이라 `!important`로 덮어씀). 로컬+NAS 둘 다 `pages.extra`에
반영 확인했지만, **실제 렌더링(여백 없이 깔끔하게 빠지는지)은 브라우저 확인 전이라 미검증** —
Vuetify 버전에 따라 padding 보정 선택자가 다를 수 있어 사용자 확인 후 조정 필요할 수 있음.

**Why:** curl/DB 확인만으로는 Vue/Vuetify가 실제로 어떻게 그리는지 알 수 없어서(이 환경엔
브라우저 도구가 없음), 최선의 추정으로 CSS를 넣고 사용자에게 시각 확인을 요청하는 방식으로
진행. 이번에도 GraphQL introspection이 아니라 `gh api`로 프론트엔드 소스를 직접 읽는 게
Wiki.js UI 동작 방식을 확인하는 유일한 방법이었음(GraphQL 스키마엔 UI 렌더링 로직이
드러나지 않음).

**How to apply:** 홈 페이지 CSS 보정이 안 맞으면(여백 남음 등) 브라우저 개발자도구로 실제
DOM 클래스를 확인해서 `scriptCss`를 다시 조정할 것 — `pages.update` mutation으로 즉시 반영
가능(재배포 불필요).

---

## 2026-08-16 | 링크 도우미 `/link/<이름>`

사용자 질문: Wiki.js 문서(특히 `guides/` 자유 문서)에 DHO 항목 링크를 걸 때마다 정확한
`dho/<category>/<item_id>` 경로를 찾아야 해서 번거로움 — `[팬시]`처럼 이름만 쓰면 자동으로
연결되는 기능이 없냐는 질문. WebSearch로 Wiki.js 공식 피드백 보드를 확인한 결과 "Auto link
creation", "Link to title", "Autocomplete links / mentions", "Succinct link syntax" 등
같은 요청이 여러 건 올라와 있었지만 전부 미해결(오픈) 상태 — Wiki.js 2.x(현재 배포 버전
2.5.314)엔 정식 기능으로 없음. 커스텀 마크다운 문법(`[link:이름]`)은 Wiki.js 마크다운
파서(markdown-it)를 플러그인으로 확장해야 해서 Wiki.js 소스/빌드까지 건드려야 함 — 이
프로젝트 규모에 비해 과함.

AskUserQuestion으로 두 가지를 확인.
1. 도구 형태 — "웹앱에 링크 도우미 페이지 추가" 선택(기존 `/search`를 확장하는 대안,
   Wiki.js 검색만 쓰는 대안, 보류 중 택1).
2. 사용자가 직접 제안한 방식 — `[link:팬시]` 입력 시 별도 페이지로 이동한 뒤 실제 위키
   문서로 이동. 표준 마크다운 링크 `[텍스트](/link/이름)` + 서버 리다이렉트로 동일한
   사용자 경험을 구현하기로 확정(문법 확장 없이 표준 마크다운만 사용).

**구현 결정**
- 매칭 기준은 `items_core.COALESCE(name, title)` 정확 일치. `get_search_results()`(기존
  `/search`)가 이미 name/title 폴백을 쓰고 있어서 그 관례를 그대로 따름 — 부분/유사 매칭은
  넣지 않음(사용자가 원한 건 "정확히 매핑되는 문서"였지 느슨한 검색이 아니었음).
- 매칭 0건/2건 이상은 같은 `link_result.html` 템플릿 하나로 처리(목록이 비어있거나 여러
  개인 경우를 분기 렌더링) — 매칭이 정확히 1건일 때만 파이썬 코드에서 바로 302.
- 리다이렉트는 서버가 아니라 **브라우저**에서 일어나므로, `build_wikijs_pages.py`가 쓰는
  내부 주소(`WIKIJS_URL`, 컨테이너 안에선 `http://wikijs:3000`)를 그대로 못 씀 — 새 env var
  `WIKIJS_PUBLIC_URL`을 추가해서 분리. `CHAT_URL`(같은 nginx origin이라 상대경로 `/chat`으로
  충분)과 달리 Wiki.js는 별도 포트(3001)라 절대 URL이 필수라는 점이 다름 — 이 차이를
  주석에 남겨둠. 실제 NAS 접속 주소 값은 사용자가 채워야 함(로컬 기본값만 코드에 넣음).

**검증**: 로컬에 떠 있던 `dho-webapp`/`dho-postgres`/`dho-wikijs` 컨테이너에 수정한
`dho_webapp.py`/`templates/link_result.html`을 `docker cp`로 올리고 컨테이너 재시작 후
실제 DB 데이터로 3가지 케이스 확인 — 유일 매칭("귀족의 모닥불" → `consumable/2964582`로
302, 리다이렉트 대상 실제 200 확인), 복수 매칭("알렉산드리아" → city/discovery 2건 목록
정상 렌더링), 매칭 없음(안내 메시지). 테스트 중 bash 헤어독(heredoc)으로 한글 문자열을
Python 스크립트에 넘겼더니 인코딩이 깨지는 문제가 재발함([[shell_korean_encoding]] 메모리와
동일 증상) — Write 도구로 UTF-8 파일을 직접 써서 실행하는 방식으로 우회.

**Why:** Wiki.js 자체를 고쳐서 `[[wikilink]]`류 문법을 지원하게 만드는 건 기술적으로는
가능하지만 이 프로젝트가 건드리는 레이어(DHO 데이터 파이프라인 + 조회 웹앱)를 벗어나
Wiki.js 코어/플러그인 영역까지 넓어짐 — 사용자가 원한 "이름만 알면 링크 가능"이라는
결과는 표준 마크다운 + 서버 리다이렉트만으로도 동일하게 달성 가능해서 더 간단한 쪽을 택함.

**How to apply:** 다음에 이 프로젝트를 다룰 때 `guides/` 자유 문서 작성 관련 요청이 오면
`/link/<이름>` 리졸버가 이미 있다는 걸 전제로 안내할 것. NAS 배포 시 `.env`에
`WIKIJS_PUBLIC_URL`을 실제 접속 주소로 채우는 걸 빠뜨리기 쉬우니 체크리스트로 남겨둠
(`checklist.md` Phase 5).
