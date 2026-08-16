# 대항해시대 온라인 DB 아카이브 (로컬)

원본 아카이브 사이트(dho-archive.vercel.app)를 크롤링한 데이터를 기반으로 직접 운영하는
**조회/편집 웹사이트**, **자연어(AI) 검색 챗봇**, **자동 생성 위키(Wiki.js)**. 프로젝트
자체는 크롤러(`scraper.py`)로 시작했지만, 지금 실제로 쓰는 결과물은 이 세 서비스다.
크롤링/구조화 과정은 아래 [데이터 파이프라인](#데이터-파이프라인-원본-크롤링--구조화-db) 절 참고.

## 구성

| 서비스 | 위치 | 설명 |
|---|---|---|
| PostgreSQL | `postgres` (docker-compose 서비스) | 구조화 데이터 + pgvector 임베딩을 담는 서빙 DB (`pgvector/pgvector:pg16`). DHO 데이터(`dho` DB)와 Wiki.js(`wikidb`)가 같은 인스턴스를 공유하되 DB는 분리 |
| 웹사이트 | `dho_webapp.py` + `templates/` + `static/` | 카테고리 → 항목 목록 → 상세(속성+표) 조회, 항목 추가/수정, 검색(`pg_trgm`), 내비게이션 순서 설정. Flask, 포트 5050. `/assistant`에서 챗봇을 iframe으로 감싸 보여주고, 항목 상세의 `/link/<name>`은 Wiki.js 문서로 리다이렉트 |
| AI 챗봇 | `chat/` | 자연어 질문에 답하는 2단계 LLM 챗봇 — 1단계(`gpt-5-mini`)가 도구 호출로 DB/위키 원본 자료를 수집하고, 2단계(`deepseek-v4-flash`)가 도구 없이 그 자료만으로 최종 답변을 종합. Text-to-SQL 조회 + 아이템/위키 pgvector 시맨틱 검색(정확한 이름을 몰라도 개념/느낌으로 검색) 지원. Next.js + Vercel AI SDK, 포트 3000 |
| Wiki.js | `wikijs` (docker-compose 서비스) + `build_wikijs_pages.py` + `build_wiki_chunks.py` | DHO 데이터를 사람이 읽는 문서로 자동 생성하는 위키(`requarks/wiki:2`). `build_wikijs_pages.py`가 구조화 DB의 항목을 Markdown 페이지로 백필/동기화(GraphQL API), `build_wiki_chunks.py`가 그 페이지를 헤더 기준으로 청킹 후 임베딩해서 챗봇의 `semantic_search_wiki` 도구에 제공. 포트 3001 |

웹사이트/챗봇은 PostgreSQL 하나(`DATABASE_URL`)만 바라보고, Wiki.js는 같은 PostgreSQL
인스턴스의 별도 DB(`wikidb`, `WIKI_DATABASE_URL`)를 쓴다. 원본 스크래핑/파싱
파이프라인(아래 [데이터 파이프라인](#데이터-파이프라인-원본-크롤링--구조화-db))은
`dho_structured.sqlite3`를 그대로 쓰고, `migrate_to_postgres.py`로 PostgreSQL에 옮긴다 —
자세한 아키텍처 배경은 `plan.md`/`context-notes.md` 참고.

## 빠른 시작 (Docker, 권장)

```bash
cp .env.example .env   # POSTGRES_*/OPENAI_*/DEEPSEEK_*/WIKI_* 값 채우기
docker compose up -d --build          # postgres + 웹사이트 + 챗봇 + wikijs 전부
docker compose up -d --build webapp   # 웹사이트만 (postgres가 이미 떠 있어야 함)
docker compose up -d --build chat     # 챗봇만
docker compose up -d --build wikijs   # Wiki.js만
```
- 웹사이트: http://localhost:5050
- 챗봇: http://localhost:3000
- Wiki.js: http://localhost:3001

최초 기동 시 PostgreSQL은 비어있으므로, 아래 [데이터 파이프라인](#데이터-파이프라인-원본-크롤링--구조화-db)의
"PostgreSQL로 이관" 단계를 한 번 실행해야 실제 데이터가 채워진다. `postgres/init.sql`은
컨테이너 최초 기동(데이터 디렉토리가 비어있을 때) 1회만 자동 실행되므로, 기존
`postgres_data` 볼륨을 재사용하는 배포에서 Wiki.js를 새로 추가한 경우 `wikidb`를 수동으로
한 번 만들어야 한다 (`CREATE DATABASE wikidb;`).

NAS 등 원격 서버로 배포하려면 `./deploy.sh` 참고 (`cp deploy.config.example deploy.config`로
접속 정보 먼저 채워야 함 — 로컬에서 먼저 빌드 검증 후 서버로 전송 + 원격 빌드까지 자동화됨).

## 로컬에서 직접 실행 (Docker 없이)

```bash
# 웹사이트 (DATABASE_URL 환경변수 필요, 예: postgresql://dho:비밀번호@localhost:5432/dho)
pip install -r requirements.txt
python dho_webapp.py                  # http://localhost:5050

# 챗봇
cd chat
cp .env.local.example .env.local      # 값 채우기 (DATABASE_URL 포함)
npm install
npm run dev                           # http://localhost:3000
```

## 데이터 파이프라인 (원본 크롤링 → 구조화 DB → PostgreSQL)

최초 1회, 또는 원본 사이트 데이터가 갱신되어 다시 받아야 할 때만 돌리면 된다.

1. **원본 HTML 캐싱** (`scraper.py`) — 전체 사이트를 크롤링해서 `dho_cache.sqlite3`에 저장
   ```bash
   pip install requests beautifulsoup4
   python scraper.py discover
   python scraper.py crawl-lists --all
   python scraper.py crawl-details --all --delay 0.8   # 33,000여 건, 수 시간 소요
   python scraper.py status
   ```
   탭 UI 뒤에 숨어서 순수 HTTP 크롤링으로 못 받은 데이터는 `scrape_hidden_tabs.py`
   (Playwright)로 추가 보강한다.

2. **구조화** (`build_structured_db.py` → `build_category_localization.py`) — 캐싱된 원본
   HTML을 `dho_structured.sqlite3`의 `items_core`/`raw_attrs`/`raw_tables`/
   `category_localization` 테이블로 파싱/변환한다. 이 2개 스크립트만 SQLite를 대상으로
   남아있다(재크롤링 시에만 도는 드문 작업이라).
   ```bash
   python build_structured_db.py stage
   python build_category_localization.py
   ```

3. **PostgreSQL로 이관** (`migrate_to_postgres.py`) — 위에서 만든 4개 "원본성" 테이블을
   PostgreSQL로 복사한다.
   ```bash
   export DATABASE_URL=postgresql://dho:비밀번호@localhost:5432/dho
   python migrate_to_postgres.py
   ```

4. **파생 테이블 생성** (`build_backlinks.py` → `build_acquisition.py` →
   `materialize_*.py` → `build_search_index.py`) — PostgreSQL 위에서 실행한다. webapp이
   항목을 저장할 때마다 이 8개를 자동으로 다시 실행하므로(`rebuild_derived_tables()`),
   최초 1회 수동 실행 이후로는 보통 webapp을 통해서만 갱신하면 된다.
   ```bash
   # DATABASE_URL 환경변수가 설정된 상태에서
   python build_backlinks.py
   python build_acquisition.py
   python materialize_generic.py   # cannon/recipe/consumable/tarotCard는 각각 전용 스크립트
   python materialize_cannon.py
   python materialize_recipe.py
   python materialize_consumable.py
   python materialize_tarotcard.py
   python build_search_index.py
   ```
   전체 33,496건 기준 로컬에서 약 1~2분 소요(대부분 `materialize_generic.py`/
   `build_acquisition.py` — 개별 INSERT가 많아 psycopg pipeline 모드를 쓰는데도 SQLite
   대비 느림. NAS에서는 더 걸릴 수 있음).

5. **아이템 임베딩 생성** (`build_embeddings.py`, 선택) — chat의 시맨틱 검색(정확한 이름을
   몰라도 개념/느낌으로 검색)을 쓰려면 필요하다. `build_search_index.py`(4번) 이후에
   실행해야 한다(그 결과물인 `items_search`를 임베딩 대상으로 재사용). `DERIVED_PIPELINE_SCRIPTS`엔
   없어서(API 비용 때문에 자동 재실행 안 함) 데이터가 크게 바뀌면 수동으로 다시 돌려야 한다.
   ```bash
   # DATABASE_URL, OPENAI_API_KEY 환경변수가 설정된 상태에서
   python build_embeddings.py
   ```
   전체 33,496건 기준 약 20~40분 소요(OpenAI API 왕복이 병목), 비용은
   `text-embedding-3-small` 기준 1회 전체 재생성에 대략 $0.2~0.3 수준.

6. **Wiki.js 문서 생성 + 청크 임베딩** (`build_wikijs_pages.py` → `build_wiki_chunks.py`,
   선택) — chat의 위키 시맨틱 검색(`semantic_search_wiki`)을 쓰려면 필요하다. `wikijs`
   컨테이너가 떠 있어야 한다.
   ```bash
   # DATABASE_URL, WIKIJS_URL, WIKI_ADMIN_EMAIL, WIKI_ADMIN_PASS 환경변수가 설정된 상태에서
   python build_wikijs_pages.py --all          # 카테고리별 Markdown 페이지 생성/갱신
   # WIKI_DATABASE_URL, OPENAI_API_KEY 환경변수가 설정된 상태에서
   python build_wiki_chunks.py                 # 페이지를 헤더 기준 청킹 + 임베딩
   ```
   `build_wikijs_pages.py`는 항목당 GraphQL 호출이라 전체 33,496건 기준 시간이 꽤 걸린다
   (`--concurrency`로 동시 처리 수 조절, 기본 8). `build_wiki_chunks.py`는 웹훅을 지원하지
   않는 Wiki.js 특성상 `wikidb.pages.hash` 변화를 폴링해서 바뀐 페이지만 재청킹한다.

## 파일 구조

```
scraper.py, scrape_hidden_tabs.py     크롤러 (원본 HTML → dho_cache.sqlite3)
build_structured_db.py,               구조화 (원본 HTML → dho_structured.sqlite3, SQLite 유지)
build_category_localization.py

migrate_to_postgres.py                dho_structured.sqlite3 → PostgreSQL 이관
pg_conn.py                            파생 테이블 스크립트 공용 Postgres 접속 헬퍼
build_backlinks.py, build_acquisition.py,  파생 테이블 생성 (PostgreSQL 대상)
materialize_*.py, build_search_index.py
build_embeddings.py                   아이템 임베딩 생성 (pgvector, chat 시맨틱 검색용)
build_wikijs_pages.py                 구조화 DB → Wiki.js Markdown 페이지 생성/동기화 (GraphQL API)
build_wiki_chunks.py                  Wiki.js 페이지 → 헤더 기준 청킹 + 임베딩 (chat 위키 시맨틱 검색용)

dho_webapp.py, templates/, static/    웹사이트 (Flask, PostgreSQL 조회/쓰기)
chat/                                 AI 챗봇 (Next.js, PostgreSQL 조회, 2단계 LLM)
openwebui_tool_dho_sql.py             (예전 OpenWebUI 연동용, chat/으로 대체됨)

postgres/init.sql                     PostgreSQL 최초 기동 시 pgvector/pg_trgm 확장 + wikidb 생성
Dockerfile, docker-compose.yml,       배포 (postgres/webapp/chat/wikijs 4개 서비스)
deploy.sh, deploy.config.example

NEXT_STEPS.md, checklist.md,          작업 기록/설계 문서
context-notes.md, CHANGELOG.md
```
