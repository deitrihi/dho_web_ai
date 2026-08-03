# 대항해시대 온라인 DB 아카이브 (로컬)

원본 아카이브 사이트(dho-archive.vercel.app)를 크롤링한 데이터를 기반으로 직접 운영하는
**조회/편집 웹사이트**와 **자연어(AI) 검색 챗봇**. 프로젝트 자체는 크롤러(`scraper.py`)로
시작했지만, 지금 실제로 쓰는 결과물은 이 두 서비스다. 크롤링/구조화 과정은 아래
[데이터 파이프라인](#데이터-파이프라인-원본-크롤링--구조화-db) 절 참고.

## 구성

| 서비스 | 위치 | 설명 |
|---|---|---|
| 웹사이트 | `dho_webapp.py` + `templates/` + `static/` | 카테고리 → 항목 목록 → 상세(속성+표) 조회, 항목 추가/수정. Flask, 포트 5050 |
| AI 챗봇 | `chat/` | 자연어 질문을 SQL로 바꿔서 검색하는 Text-to-SQL 챗봇. Next.js + Vercel AI SDK, 포트 3000 |

두 서비스 모두 `dho_structured.sqlite3`(구조화된 DB, 211개 테이블) 하나를 공유해서 읽는다.

## 빠른 시작 (Docker, 권장)

```bash
cp .env.example .env   # 챗봇용 OPENAI_API_BASE_URL/KEY/MODEL 값 채우기
docker compose up -d --build          # 웹사이트 + 챗봇 둘 다
docker compose up -d --build webapp   # 웹사이트만
docker compose up -d --build chat     # 챗봇만
```
- 웹사이트: http://localhost:5050
- 챗봇: http://localhost:3000

NAS 등 원격 서버로 배포하려면 `./deploy.sh` 참고 (`cp deploy.config.example deploy.config`로
접속 정보 먼저 채워야 함 — 로컬에서 먼저 빌드 검증 후 서버로 전송 + 원격 빌드까지 자동화됨).

## 로컬에서 직접 실행 (Docker 없이)

```bash
# 웹사이트
pip install -r requirements.txt
python dho_webapp.py                  # http://localhost:5050

# 챗봇
cd chat
cp .env.local.example .env.local      # 값 채우기
npm install
npm run dev                           # http://localhost:3000
```

## 데이터 파이프라인 (원본 크롤링 → 구조화 DB)

최초 1회, 또는 원본 사이트 데이터가 갱신되어 다시 받아야 할 때만 돌리면 된다. 결과물인
`dho_structured.sqlite3`는 git에 안 올라가므로(수백MB) 이 과정을 거쳐 직접 만들거나,
이미 만들어진 파일을 서버 등에서 복사해와야 한다.

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

2. **구조화** (`build_structured_db.py` → `build_acquisition.py` → `materialize_*.py` →
   `build_backlinks.py` → `build_category_localization.py`) — 캐싱된 원본 HTML을
   `dho_structured.sqlite3`의 관계형 테이블로 파싱/변환한다.
   ```bash
   python build_structured_db.py stage
   python build_acquisition.py
   python materialize_generic.py   # cannon/recipe/consumable/tarotCard는 각각 전용 스크립트
   python build_backlinks.py
   python build_category_localization.py
   ```

## 파일 구조

```
scraper.py, scrape_hidden_tabs.py     크롤러 (원본 HTML → dho_cache.sqlite3)
build_structured_db.py, build_*.py,   구조화 (원본 HTML → dho_structured.sqlite3)
materialize_*.py

dho_webapp.py, templates/, static/    웹사이트 (Flask)
chat/                                 AI 챗봇 (Next.js)
openwebui_tool_dho_sql.py             (예전 OpenWebUI 연동용, chat/으로 대체됨)

Dockerfile, docker-compose.yml,       배포
deploy.sh, deploy.config.example

NEXT_STEPS.md, checklist.md,          작업 기록/설계 문서
context-notes.md, CHANGELOG.md
```
