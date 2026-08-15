# DHO 로컬 아카이브 프로젝트 — 다음 작업 (TODO)

## 현재까지 진행된 것
- `scraper.py`: dho-archive.vercel.app 전체를 크롤링해서 `dho_cache.sqlite3`에
  원본 HTML을 캐싱하는 스크립트 (목록 페이지 → id/이름 수집, 상세 페이지 → 원본 HTML 저장)
- 전체 사이트 크롤링 완료 (33,496 / 33,496건, 2026-07-31)

크롤링이 끝나면 `dho_cache.sqlite3`에는:
- `pages` 테이블: URL별 원본 HTML 전체
- `categories` 테이블: 70개 카테고리 목록/건수
- `items` 테이블: 카테고리별 항목 id/이름, 크롤링 완료 여부

가 저장된다 (원본 HTML 캐시). 이걸 구조화한 결과물은 `dho_structured.sqlite3`에 있다
(아래 "다음 단계 1" 완료 항목 참고).

---

## 다음 단계 1 — 구조화 DB 스키마 설계 및 파싱 (완료, 2026-07-31)

`pages` 테이블에 캐싱된 원본 HTML을 실제 관계형 스키마로 파싱해서 `dho_structured.sqlite3`로
옮기는 작업. **70/70 카테고리 전부 완료**, 총 211개 테이블. 자세한 내용은 `checklist.md`,
`context-notes.md` 참고.

- [x] 카테고리별 상세 페이지 HTML 구조 분석 (테이블/속성/링크 패턴) — 전체 사이트가
      "속성-값 행 + 표" 구조를 일관되게 씀을 확인
- [x] 카테고리별 스키마 설계 — 참고 ERD 없이 원본 사이트 구조를 그대로 반영
- [x] 공통 관계 테이블 설계·구현 — 획득처(판매NPC/레시피/퀘스트/보물지도 등), 변성연금,
      필요/보상(종류-내용) 패턴을 카테고리 공유 테이블로 분리 (`build_acquisition.py`)
- [x] 카테고리별 파서 작성 — cannon/recipe/consumable/tarotCard 4개는 수작업 검증,
      나머지 66개는 `materialize_generic.py`로 자동 생성 (한글 라벨 컬럼명, 자동 타입판별)
- [x] 파싱 결과를 `dho_structured.sqlite3`에 적재
- [x] 대표 샘플 원본 대조 검증 (cannon/recipe/consumable/tarotCard 전수, ship/equipment/city
      샘플) — 전부 일치. 자동화 66개의 알려진 한계(쉼표 포함 숫자 TEXT 처리 등)는
      `checklist.md` 참고, 필요시 카테고리별로 선별 개선 가능

## 다음 단계 2 — 로컬 LLM 검색 구조 구축 (거의 완료, 2026-08-01~02)

- [x] 검색 방식 결정: Text-to-SQL (OpenWebUI Tool 방식, `openwebui_tool_dho_sql.py`)
- [x] OpenWebUI + Ollama Docker Compose 구축 → 이후 NAS 이전 대비 Ollama 제거하고
      OpenAI 호환 API(gpt-5-mini)로 전환 (`docker-compose.yml`, `.env.example`)
- [x] Tool 함수 구현: `list_categories`/`find_tables`/`get_table_schema`/`run_sql`/
      `search_items`/`get_item_detail` — read-only 커넥션 + SELECT 전용 + 인젝션 차단
- [x] `get_item_detail`이 카테고리 전용 테이블뿐 아니라 `item_acquisition_*`/
      `item_transmutation_*` 공유 테이블까지 자동 조인하도록 개선 (모델이 멀티테이블 조인을
      스스로 못 찾는 문제 해결)
- [x] 로컬 qwen2.5:7b → OpenAI gpt-5-mini로 전환, 실사용 테스트("준사관 우대 스킬",
      "해양조합 등록증 해상 NPC 획득처") 검증 완료
- [x] **OpenWebUI 프론트엔드를 Vercel AI SDK 기반 직접 구축 프론트로 교체 (2026-08-03)**:
      사용자 요청으로 `chat/` 서브프로젝트 신규 생성 (Next.js App Router + `ai`/
      `@ai-sdk/react`/`@ai-sdk/openai`). `openwebui_tool_dho_sql.py`의 6개 Tool 함수를
      `chat/lib/dho-db.ts`로 그대로 포팅(Node.js 내장 `node:sqlite`로 `dho_structured.sqlite3`
      읽기 전용 접근). `app/api/chat/route.ts`에서 `streamText` + `stopWhen: stepCountIs(8)`로
      멀티스텝 도구 호출 지원, `app/page.tsx`에 다크 테마 채팅 UI 구현.
      Next.js 16.2.12(설치 당시 최신, 학습 데이터 이후 버전)라 `node_modules/next/dist/docs`를
      직접 읽어 API 확인하며 작업. `convertToModelMessages`가 이제 비동기(Promise 반환)로
      바뀐 것, `node:sqlite` 타입을 쓰려면 `@types/node`를 22+ 로 올려야 하는 것 등
      버전 관련 이슈 몇 개 확인/수정. API 키 없이 구조적 검증만 완료(라우팅·도구 정의·DB
      접근 전부 정상 동작 확인, 실제 모델 호출 직전 `AI_LoadAPIKeyError`로 막힘) —
      `chat/.env.local`에 실제 API 키를 채워야 실사용 테스트 가능
- [x] **NAS(원격 서버) Docker 배포 구성 (2026-08-03)**: `chat/Dockerfile`(Next.js
      `output: "standalone"` + node:24-alpine 멀티스테이지), `chat/.dockerignore` 신규.
      `docker-compose.yml`의 openwebui 서비스를 chat 서비스(`build: ./chat`)로 교체 —
      `dbsql/` 폴더 전체를 컨테이너에 `/data/dbsql`로 읽기 전용 마운트, `.env.example`도
      `OPENWEBUI_*` → `OPENAI_*`로 변수명 정리. 로컬에서 `docker compose build chat`
      빌드 성공 확인, `docker run`으로 컨테이너 기동 후 실제 OpenAI API 엔드포인트까지
      요청이 도달하는 것 확인(플레이스홀더 키라 401 응답 — 배선은 정상, 실응답은
      미검증). 로컬 테스트 중 예전 openwebui/ollama 컨테이너가 고아 상태로 남아 포트
      3000을 점유하고 있는 걸 발견했는데, 사용자가 "다른 서버에 배포할 것"이라고 확인해줘서
      로컬 컨테이너는 그대로 두고 안 건드림. `chat/README.md`에 NAS 배포 절차(rsync로
      프로젝트 전송 → `.env` 준비 → `docker compose up -d --build chat`) 정리
- [x] **NAS 실제 배포 및 배포 후 버그 3건 수정 (2026-08-03)**: 사용자 Synology NAS
      (`/volume1/docker/dho_chat`)에 SMB로 프로젝트 복사 후 실배포하며 발견된 문제들.
      1) robocopy `/XD`에 `chat\node_modules`처럼 백슬래시 포함 상대경로를 넘기면 매칭이
         안 돼서 node_modules/.next/.git이 그대로 복사됨 → NAS에서 직접 삭제, 이후엔
         `/XD`에 바로 이름만(`node_modules` `.next` `.git`) 넘겨야 함을 확인
      2) NAS 목적지에 2026-07-31자 기존 `.env`(진짜 API 키 포함, `OPENWEBUI_*` 변수명)가
         이미 있었음 — `Get-ChildItem`이 기본적으로 숨김 파일을 안 보여줘서 처음엔 폴더가
         빈 걸로 오인함(`-Force` 필요). 키 값은 안 건드리고 `OPENAI_*`로 변수명만 현지
         파일에서 바로 치환
      3) 배포 후 모든 질문이 스트리밍 없이 바로 500 — 로그 확인 결과
         `AI_InvalidArgumentError: baseURL must be a non-empty string`가 모듈 평가
         시점에 발생. 원인: `createOpenAI()`를 라우트 파일 최상단(모듈 로드 시점)에서
         호출해서, Docker 빌드 시점엔 환경변수가 없었던 탓에 Next.js가 `process.env.
         OPENAI_API_BASE_URL`을 빈 값으로 빌드 결과물에 인라인해버림 — 컨테이너 실행
         시 docker-compose가 넣어주는 진짜 런타임 환경변수를 계속 무시함.
         `createOpenAI()` 호출을 POST 핸들러 안(요청 처리 시점)으로 이동해서 해결.
         로컬에서 "빌드 타임엔 환경변수 없음 + 실행 시점에만 있음"인 동일 시나리오로
         재현/검증 완료
      4) route.ts 수정 후 재배포하니 "데이터베이스 파일을 열 수 없음"으로 도구 호출이
         실패(AI SDK가 우아하게 처리해서 docker logs엔 안 남음, 모델 응답에만 드러남).
         컨테이너 안에서 직접 `ls`+`node:sqlite` 오픈 테스트해보니 `Permission denied`
         — Windows SMB로 복사된 `dho_structured.sqlite3`를 컨테이너 비루트 사용자
         (uid 1001)가 못 읽는 상태였음. `sudo chmod -R a+rX /volume1/docker/dho_chat`로
         해결. **주의**: 앞으로 DB를 재스테이징해서 SMB로 다시 동기화할 때마다 이 chmod를
         다시 실행해야 할 수 있음
      최종 확인: 사용자가 "잘 실행되고 있어" 확인
- [ ] 남은 것: 더 다양한 실사용 질문으로 회귀 테스트, 기존 로컬(Windows) openwebui/ollama
      컨테이너 정리 여부 결정, 모델의 SQL 조인 실패 패턴이 또 나오면 get_item_detail류
      헬퍼 추가 검토

## 다음 단계 3 — 스크래핑 데이터 완전성 (완료, 2026-08-01)

3단계 실사용 테스트 중 "획득 방법" 탭 UI(퀘스트/아이템 사용/해상 NPC 등)에서 비활성 탭 데이터가
원본 스크래핑에서 통째로 빠져있던 것을 발견 (전체 33,496건 중 3,365건, 약 10% 영향).
`scrape_hidden_tabs.py`(Playwright)로 해당 항목만 추가 크롤링 후 `build_acquisition.py`/
`materialize_*.py` 재실행으로 반영 완료. 자세한 경위는 `context-notes.md` 참고.

## 다음 단계 4 — 로컬 조회용 웹앱 (진행 중, 2026-08-02 시작)

원본 사이트(dho-archive.vercel.app)와 동일한 정보 구조를 보여주는 Flask 기반 조회 전용
웹앱. LLM 없이 그냥 브라우징하고 싶을 때 사용.

- [x] `dho_webapp.py` + `templates/` + `static/style.css` — 카테고리 목록 → 항목 목록 →
      상세(속성+표) 3단 구조, `items_core`/`raw_attrs`/`raw_tables`만으로 렌더링
- [x] `build_category_localization.py` — 카테고리 한글명 + 6개 대분류(모험/아이템/선박/
      인물 · 스킬/NPC/세계) 매핑을 원본 사이트 JS 번들에서 추출해 별도 로컬라이제이션
      테이블(`category_localization`)로 저장, 원본 데이터는 안 건드림
- [x] 홈 화면 대분류 그룹핑 + 카테고리 목록/상세 페이지 브레드크럼 한글화 적용 및 검증
      (cannon→대포, certificate→추천장, equipment→장비품 등)
- [x] **표 셀 텍스트 가독성 문제 수정 (2026-08-02)**: 원인은 `parse_cell()`의
      `get_text("\n", strip=True)` — 인라인 링크/툴팁 경계마다 텍스트 조각을 개별 strip한 뒤
      "\n"으로 이어붙이면서 원본 텍스트 노드가 갖고 있던 공백("모험 | ", " ( 4 " 등)이
      사라진 게 원인이었음. 원본 사이트 캐시 HTML을 직접 대조해보니 텍스트 노드 자체에
      필요한 공백이 이미 포함돼 있어서, 구분자 없이 `get_text().strip()`으로 이어붙이기만
      해도 원본과 동일하게 읽힘을 확인. 수정 후 `stage` + `build_acquisition.py` +
      `materialize_*.py` 전체 재실행 완료, equipment/6582·consumable/1016856 등 샘플로
      로컬(:5050) vs 원본(dho-archive.vercel.app) 대조 검증함
- [x] **디자인을 원본 사이트 레이아웃에 맞춰 재작성 (2026-08-02)**: 캐시된 원본 HTML의
      Tailwind 클래스를 직접 대조해서 구조 파악 (스크린샷 없이 진행) — 좌측 220px 사이드바
      (로고 + 대분류 6개 접이식 내비게이션), 상단 헤더바 + 브레드크럼 바, 상세 페이지는
      카드 섹션(제목+카테고리뱃지, 설명 박스, 속성 2단 그리드, 라운드보더 표) 구조로
      `templates/base.html`/`item.html`/`category.html`/`index.html`/`static/style.css`
      전면 재작성. 색상 팔레트는 기존 것 그대로 유지(라이트/다크 CSS 변수 안 건드림).
      카테고리 목록 페이지는 원본처럼 카테고리별 통계 컬럼 정렬 테이블로 만들지, 지금처럼
      단순 목록으로 할지 사용자에게 물어봤고 "단순 목록 우선"으로 결정 — 통계 컬럼 테이블은
      카테고리 70개마다 어떤 속성을 컬럼으로 보여줄지 스키마 판단이 필요한 별도 작업으로
      보류. Playwright로 라이트/다크 스크린샷 찍어서 렌더링 검증, `.links`가 `<td>`의
      `white-space:pre-wrap`을 상속해서 링크마다 줄바꿈되던 CSS 버그도 같이 발견/수정
- [x] **상세 페이지 속성 영역을 2단 그리드 → 단일 컬럼 리스트로 재변경 (2026-08-02)**:
      사용자가 원본 사이트 스크린샷(quest/15390, "피에 굶주린 폭군")을 캡처해서 제공 —
      2단으로 나뉘어 배치되던 걸 원본처럼 라벨-값이 한 줄씩 쌓이는 리스트로 바꿔달라는
      요청. `attr-grid`(CSS grid 다단)를 제거하고 속성+표를 `.row-list` 하나로 통합해서
      전부 같은 라벨 폭(120px)으로 한 줄씩 정렬되게 변경
- [x] **순서 불일치 + 이미지 속성 데이터 버그 수정 (2026-08-02)**: 위에서 발견한 두 이슈
      모두 수정.
      1) 순서 불일치 — `extract_detail()`이 `main.select("div.flex.gap-4")` 순회 중 각
         attr/table에 순번(`position`)을 매기도록 수정, `raw_attrs`/`raw_tables`에
         `position` 컬럼 추가(SCHEMA_VERSION 3). `dho_webapp.py`의 `item_detail()`이
         attrs+tables를 `position` 기준으로 병합한 단일 `rows` 리스트로 넘기도록 재작성,
         `templates/item.html`도 `rows` 하나만 순서대로 순회하도록 변경. quest/15390에서
         "필요"/"보상" 표가 이제 "분류"/"난이도" 바로 다음에 나오는 것 확인
      2) 이미지 데이터 버그 — 원인은 "이미지" 행 자체가 `<figure><img>+<figcaption>`
         구조였는데 `parse_cell()`의 `get_text()`가 `<figcaption>` 텍스트("공략")까지
         주워서 text 필드에 캡션 글자가 잘못 섞여 들어간 것(라벨/값 매칭 문제가 아니었음).
         `parse_cell()`이 figure를 먼저 뽑아 `images`(src/alt/caption) 리스트에 담고
         트리에서 제거한 뒤 나머지 텍스트를 추출하도록 수정, `raw_attrs.images_json` 컬럼
         추가. 이미지 URL은 원본이 쓰는 supabase storage 공개 URL을 그대로 참조(핫링크,
         로컬 다운로드/캐싱은 안 함). `templates/item.html`/`static/style.css`에
         이미지 렌더링 추가. quest/15390에서 실제 지도 이미지가 뜨는 것 확인
      수정 후 전체 재스테이징 + `build_acquisition.py` + `materialize_*.py` 재실행 완료
- [x] **전체 70개 카테고리 스타일/엣지케이스 검토 (2026-08-03)**: 소규모 샘플로만
      확인했던 걸 "나머지 전체 데이터에 대해서 구현해줘" 요청으로 전체 33,496건에 대해
      점검. Flask test_client로 전체 상세 페이지를 순회하는 스모크 테스트(500 에러 0건)
      + 라벨 길이/표 헤더 개수/이미지 개수 극단값 데이터로 시각 검증. 아래 3개 추가
      이슈 발견 및 수정.
      1) 긴 한글 라벨이 음절 중간에서 줄바꿈되는 문제(예: "오른쪽" → "오"+"른쪽") —
         `body`에 `word-break: keep-all` 추가로 해결
      2) 표 셀 안에 중첩 `<table>`이 있는 케이스(discovery "논전 콤보"/"장식품", quest
         "필요" — 총 1,345건) — `build_structured_db.py`의 표 파싱이 재귀 탐색이라
         중첩 표의 행/셀까지 바깥 표 것처럼 잘못 섞여 들어가서 헤더-셀 개수 불일치(전체
         2,721건) 및 중복 유령 행이 생기던 버그. `tbody`/`tr`의 직계 자식만 골라 담도록
         스코프 제한하고, 중첩 표는 `parse_cell()`에서 ", "로 이어붙인 인라인 텍스트로
         펼치도록 수정 — 수정 후 불일치 0건 확인
      3) 속성값에 원본이 의도한 개행이 있는 케이스(예: "연결 지도/퀘스트"에 퀘스트
         후보가 여러 개 나열될 때 줄바꿈 없이 붙어 보이던 문제) — `.row-value`에
         `white-space: pre-wrap` 추가로 해결하려다가, Jinja 템플릿의 `{% %}` 블록
         사이 들여쓰기 공백이 그대로 노출되어 속성 행마다 빈 줄이 생기는 재발 버그
         발견 → `dho_webapp.py`에 `trim_blocks`/`lstrip_blocks` 설정을 추가해서
         근본 원인(템플릿이 렌더링에 불필요한 공백을 남기는 것)을 고침
      전체 재스테이징 + `build_acquisition.py` + `materialize_*.py` 재실행, 최종
      스모크 테스트로 500 에러 0건 재확인
- [x] **백링크 섹션 "이 항목을 참조하는 곳" 구현 (2026-08-03)**: `build_backlinks.py`
      신규 — raw_attrs.links_json/raw_tables 셀 링크를 전부 스캔해서 정방향 링크를
      뒤집은 `item_backlinks` 테이블(target/source category·item_id·label) 생성
      (440,926건). 원본 사이트의 정확한 내부 집계 로직은 알 수 없어서 "다른 항목이 이
      항목으로의 링크를 갖고 있으면 backlink"라는, 우리가 가진 데이터로 명확히 계산
      가능한 정의를 씀. equipment/6582에서 검증해보니 스킬 "사교"/"회피"가 자기 페이지의
      "장비품" 속성으로 6582를 링크하고 있어서 backlink로 잡히는 것 확인 — 원본 사이트의
      "참조하는 곳" 섹션과 같은 종류의 관계로 보임. `dho_webapp.py`의 `get_backlinks()`가
      소스 카테고리별로 묶어서 뱃지(개수)+목록 형태로 반환, 흔한 스킬/재료는 backlink가
      수천 건(최대 6,468건)이라 카테고리당 30건까지만 보여주고 나머지는 "OO 외 N건 더"로
      표시. `templates/item.html`/`static/style.css`에 섹션 추가. Jinja에서 dict 키를
      "items"로 쓰면 `dict.items()` 내장 메서드와 충돌해서 렌더링이 깨지는 것 발견 →
      "entries"로 변경
- [x] **카테고리 목록 페이지 통계 컬럼 + 정렬 표 구현 (2026-08-03)**: raw_attrs에서
      카테고리별 속성 라벨의 평균 글자 수를 계산해서, 짧고(≤20자) 분류값스러운 속성만
      최대 7개까지 목록 표의 컬럼으로 자동 선정하는 휴리스틱(`get_list_columns()`)으로
      구현 — 원본처럼 70개 카테고리를 전부 수작업으로 스키마 큐레이션하는 대신 자동
      선정. 장문 속성(quest의 "진행"/"공략" 등)은 자연히 제외됨. 컬럼 값이 전부 숫자
      패턴이면 정렬 시 `CAST(... AS INTEGER)`로 진짜 숫자 정렬, 아니면 텍스트 정렬.
      헤더 클릭으로 정렬(`?sort=라벨&dir=asc|desc`), 현재 정렬 컬럼엔 ▲▼ 표시.
      SQL 인젝션 방지를 위해 `sort` 파라미터는 실제 컬럼 라벨 화이트리스트와 대조 후에만
      raw SQL에 사용. 속성이 없는 카테고리(과거 tarotCard 전용 테이블처럼 컬럼이 없는
      경우는 없었음 — raw_attrs 기반이라 있으면 다 잡힘)는 이름만 있는 기존 단순 목록으로
      자동 폴백. 70개 카테고리 전체 + 각 컬럼 + 양방향 정렬 조합을 스모크 테스트해서
      에러 0건 확인
- [x] Docker화해서 NAS docker-compose 스택에 서비스로 추가 (2026-08-03, NAS 배포 완료)

## 다음 단계 5 — 마무리
- [ ] 크롤링 스크립트를 주기적 재크롤링(업데이트 감지)용으로 확장할지 결정
- [ ] 전체 파이프라인 문서화 (크롤링 → 파싱 → 검색 → 웹앱)

## 다음 단계 6 — SQLite → PostgreSQL 전환 + pgvector 시맨틱 검색 (완료, 2026-08-10)

`dho_structured.sqlite3` 기반이던 webapp/chat을 PostgreSQL 하나로 통합하고, chat에 아이템
시맨틱(벡터) 검색을 추가한 대규모 작업. **Phase 1(Postgres 마이그레이션)과 Phase 2(pgvector
임베딩) 전부 완료, 로컬+NAS 배포/검증까지 끝남.** 상세 설계/결정 근거는 `plan.md`,
진행 체크리스트는 `checklist.md`, 세부 판단 로그는 `context-notes.md`와
`claude_logs/postgresql-마이그레이션-phase1.md` 참고 — 이 프로젝트를 다시 다룰 때는
`checklist.md`의 Phase 3(Wiki.js) 항목부터 이어가면 된다.

- [x] **Phase 1 — PostgreSQL 마이그레이션**: `migrate_to_postgres.py`(SQLite "원본성" 4개
      테이블 이관) + 파생 테이블 8개 스크립트를 psycopg로 재작성(Postgres 대상) +
      `chat/lib/dho-db.ts`(pg 드라이버) + `dho_webapp.py`(psycopg) 재작성. `items_fts`
      (SQLite FTS5)는 `pg_trgm` 기반 `items_search`로 교체. notion-sync 기능(사용자 요청으로
      불필요해짐)은 완전 제거. NAS 배포 완료(포트 충돌 등 이슈 해결, 데이터 이관 검증 완료).
- [x] **Phase 2 — pgvector 아이템 시맨틱 검색**: `build_embeddings.py`(OpenAI
      text-embedding-3-small)로 33,496개 항목 전부 임베딩 생성, `item_embeddings`(HNSW
      코사인 인덱스) 구축. `chat`에 `semantic_search_items` 도구 추가 — 정확한 이름을 몰라도
      개념/느낌으로 아이템 검색 가능. 로컬+NAS 양쪽 다 임베딩 생성 및 실사용 질문 검증 완료.
- [x] **Phase 3 — Wiki.js 배포 + 콘텐츠 생성 + 청크 임베딩 (완료, 2026-08-10~15)**:
      docker-compose에 `wikijs` 서비스 추가, `build_wikijs_pages.py`(DHO 데이터→Markdown
      +GraphQL 생성/갱신)/`build_wiki_chunks.py`(헤더 기준 청킹+임베딩, 웹훅 미지원이라
      `wikidb.pages.hash` 폴링) 구현. chat에 `semantic_search_wiki` 도구 추가(DB 원본
      grounding 포함). 70개 카테고리 전체(33,496건) 백필 + 125,328개 청크 임베딩 로컬
      완료(백필 도중 Wiki.js 동시쓰기 버그, 로컬 Docker Desktop 다운, 페이지 누적에 따른
      저장 지연/타임아웃을 순서대로 발견·수정하며 진행 — 상세는 `context-notes.md`).
      NAS엔 재백필 대신 로컬에서 검증된 DB(`wikidb` + `wiki_chunks`/`wiki_page_state`/
      `wiki_chunk_sync_state`)를 `pg_dump`/`pg_restore`로 그대로 이관, NAS
      `semantic_search_wiki` 실사용 질문으로 재검증 완료. 로컬/NAS 양쪽 다 서빙 준비 끝남.
      상세: `plan.md`/`checklist.md`/`context-notes.md`의 Phase 3 항목,
      `claude_logs/phase3-wikijs-배포-청크임베딩.md`.
