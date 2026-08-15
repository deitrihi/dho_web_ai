# Claude 작업 로그 — Phase 3: Wiki.js 배포 + 콘텐츠 생성 + 청크 임베딩

## 2026-08-10 | Phase 3 착수 및 로컬 종단간 구현

### 요청
- "phase 3을 진행해줘" — plan.md/checklist.md에 이미 설계돼 있던 Wiki.js 배포+콘텐츠
  생성+청크 임베딩 단계를 실제로 구현.

### 행동
- `docker-compose.yml`에 `wikijs` 서비스 추가(`ghcr.io/requarks/wiki:2`), `postgres/init.sql`에
  `wikidb` 생성 구문 추가(기존 볼륨엔 수동 `CREATE DATABASE` 1회 필요).
- Wiki.js 설치 마법사 자동화: `ADMIN_EMAIL`/`ADMIN_PASS` 환경변수는 공식 이미지에서
  동작하지 않음을 확인 → `gh api`로 `requarks/wiki` 소스(`server/setup.js`)를 직접 읽어서
  `POST /finalize`(adminEmail/adminPassword/siteUrl/telemetry) 하나로 마법사를 완전히
  대체할 수 있음을 확인하고 구현.
- GraphQL 인증은 `authentication.login` mutation의 JWT(30분 만료, 20분마다 재로그인)를
  사용. `pages.create`/`update`/`singleByPath` 스키마는 introspection으로 실측 검증.
- `build_wikijs_pages.py` 신규: DHO `items_core`/`raw_attrs`/`raw_tables`를 Markdown으로
  변환(속성은 `## 속성` 리스트, 표는 `### <표 이름>` 마크다운 표, 링크는
  `/dho/<category>/<item_id>` 위키 경로로 치환 — `dho_webapp.py`의
  `render_text_with_links()`와 동일 로직) 후 GraphQL로 페이지 생성/갱신. 콘텐츠 해시를
  `wiki_page_state` 테이블에 저장해서 변경 없는 항목은 스킵(idempotent).
- 파일럿(tarotCard 22건, dungeon 35건 — 링크/표/이미지 전부 포함하는 대표 케이스)으로
  검증: 링크 치환, 표 렌더링, 이미지 임베드 전부 육안 확인.
- `build_wiki_chunks.py` 신규: Wiki.js는 웹훅을 지원하지 않음(2026-08 기준 확인, 이슈
  트래커에 기능 요청으로만 존재) → `wikidb.pages.hash`(Wiki.js가 저장 시 갱신하는 내부
  해시) 비교 기반 폴링으로 변경 감지. 마크다운 헤더(`#`/`##`/`###`) 기준으로 섹션 단위
  청킹, 페이지 제목을 접두어로 붙여 임베딩(`item_embeddings`의 embedded_text 패턴과
  동일). `wiki_chunks` 테이블(category/item_id nullable, HNSW 인덱스) + 삭제 페이지 정리.
- 종단간 검증(로컬): 58페이지 → 250청크 임베딩 → "이집트 피라미드 안에서 탐험할 수 있는
  유적" 질의 → "기자 피라미드 중계층" 1위로 정확히 검색됨.
- `chat/lib/dho-db.ts`에 `semanticSearchWiki()` 추가(category/item_id 있으면 `items_core`
  조인해서 `grounded_item` 반환), `route.ts`에 `semantic_search_wiki` 도구 등록 + 시스템
  프롬프트에 "사실 근거는 grounded_item 우선" 규칙 추가. `npm run build` 통과, 실제 chat
  API(`/chat/api/chat`)로 "기자 피라미드 던전" 질문 테스트 → 도구 호출 → grounded_item
  포함한 정확한 한국어 답변 확인.
- 파일럿 검증 완료 후 `build_wikijs_pages.py --all`(전체 70개 카테고리, 33,496건)을
  백그라운드로 실행 착수.

### 결정
- Wiki.js 공식 이미지는 서드파티 포크와 달리 env var 기반 무인 설치를 지원하지 않아서,
  소스 코드를 직접 읽어 `POST /finalize` 재현 방식으로 우회 — 검색 결과보다 소스 확인이
  더 신뢰할 수 있는 근거였음.
- 웹훅 미지원이 확정되어 리스크 항목 해소 — 폴링 주기는 NAS 배포 시 사용자와 상의 필요
  (아직 결정 안 됨).
- 청킹은 문서 구조(자동 생성 페이지든 사람이 쓰는 자유 페이지든)의 헤더만 있으면 동일하게
  동작하도록 설계 — 페이지 종류별 특수 처리 없음.

### 해결된 문제
- curl로 한글 GraphQL 요청을 보낸 뒤 `psql` 결과가 깨져 보여서 인코딩 버그로 의심했으나,
  `encode(col::bytea,'hex')`로 원시 바이트를 대조해 실제로는 정상 UTF-8이었고 Git Bash
  콘솔 표시 문제였을 뿐임을 확인(memory: 이 환경 curl 한글 이슈 — 이번엔 curl도 Python도
  둘 다 정상이었고 순수 터미널 렌더링 문제였음, 구분법을 새로 기록해둠).
- Windows에서 `os.execve`/부모가 먼저 종료하는 `subprocess.Popen` 방식으로 백그라운드
  실행 시 하네스가 실제 작업 프로세스를 추적 못 하고 "completed"를 조기 보고하는 현상을
  발견 — DB를 직접 폴링해서 실제로는 계속 진행 중임을 확인, 완료 알림에 의존하지 않기로.

### 미해결 (2026-08-10 시점, 이후 해결됨 — 아래 추가 로그 참고)
- `build_wikijs_pages.py --all` 전체 실행 진행 중(백그라운드, 완료까지 수 시간 예상) —
  완료 후 `build_wiki_chunks.py` 전체 실행 필요.
- NAS 배포 미착수 — 리소스(메모리/디스크) 확인, `deploy.sh`에 Wiki.js 초기화(`POST
  /finalize`) 단계 반영, `wikidb` 수동 생성, 청크 폴링 스크립트 cron 등록까지 필요.
  사용자 확인 후 진행 예정.
- 청킹 크기 상한(`MAX_TEXT_CHARS` 6000자 절단 외 별도 분할 로직 없음)이 전체 데이터
  확대 후에도 적절한지 재확인 필요.

---

## 2026-08-11~15 | 전체 백필 + NAS 배포 완주

### 요청
- 전체 카테고리 백필 진행 상황 확인 요청이 며칠에 걸쳐 반복됨, 도중 "deepseek로 모델
  바꾸면 어떨지" 질문(나중으로 보류), NAS에 wiki 설치 요청.

### 행동
- **동시성 버그 발견/수정(2026-08-10~11)**: `--concurrency`로 페이지 생성을 병렬화했더니
  Wiki.js 2.5.314의 내부 "rebuild-tree" 작업이 동시 요청을 못 견디고 `pageTree` 제약조건
  위반으로 깨짐(cannon 566건 중 75건, certificate 70건 중 42건 실패). 마크다운 생성(DB
  조회)은 병렬 유지하되 실제 Wiki.js 쓰기(create/update)만 전역 락으로 직렬화하도록
  수정 — 재검증 결과 실패 0건.
- **chat 도구 중복 호출 버그 수정(2026-08-11)**: 사용자가 공유한 스크린샷("플레이트
  아머 재료+구매처" 질문)에서 `get_item_detail` 호출 후 같은 키워드로 `search_items`를
  또 불러 호출 한도(`stepCountIs(16)`)를 낭비하는 문제 발견. 시스템 프롬프트에 중복
  호출 금지 규칙 추가 + 한도를 24로 상향, 동일 질문 재현으로 검증(호출 10회+ 실패 → 4회
  정상 완료).
- **NAS Wiki.js 인프라 배포(2026-08-11)**: 로컬 백필과 병행해서 NAS에 `wikijs` 서비스
  배포 — `./deploy.sh`(전체 서비스) → `wikidb` 수동 생성 → `POST /finalize`로 브라우저
  없이 설치 마법사 완료. 이 시점엔 빈 Wiki.js만 설치, 데이터는 로컬 백필 완료 후 이관하기로
  결정(사용자 선택: NAS 재백필 대신 `pg_dump`/`restore`로 로컬 검증본 이관).
- **로컬 Docker Desktop 다운(2026-08-11~12 사이)**: 원인 불명(사용자 PC 재부팅/절전 등
  추정)으로 `com.docker.service`가 멈춰 백필 프로세스가 `psycopg.OperationalError`로
  죽어있던 걸 발견(하네스의 "completed" 알림이 뒤늦게, 부정확하게 도착 — Windows에서
  자식 프로세스를 직접 실행한 경우엔 정확했지만 이전 `os.execve` 방식에서 이미 알려진
  PID 불일치 문제와는 별개로, 이번엔 진짜 크래시였음). `Docker Desktop.exe` 재기동 후
  전 컨테이너가 `restart: unless-stopped` 정책으로 자동 복구, 데이터 손실 없음 확인
  후 백필 재개.
- **페이지 누적에 따른 타임아웃(2026-08-13~14)**: 백필 후반부(skill 카테고리 등)에서
  Wiki.js 저장이 느려지며(`docker stats`로 CPU 111% 확인 — 페이지 3만 개 이상 누적되며
  검색 인덱싱/트리 갱신 비용 증가로 추정) 기본 30초 타임아웃 초과 실패가 급증(누적
  413건). `REQUEST_TIMEOUT`을 `WIKIJS_REQUEST_TIMEOUT` 환경변수로 바꾸고 90초로 늘려
  실패 항목만 재시도 → 전부 성공. **최종 33,496/33,496건 100% 완료**.
- **전체 청크 임베딩(2026-08-14)**: `build_wiki_chunks.py` 전체 실행, 33,439개 변경
  페이지 → 125,328개 청크 임베딩 완료(약 8시간 소요, OpenAI 배치 API 호출이라 Wiki.js
  쓰기보다 훨씬 빠름).
- **NAS 데이터 이관(2026-08-14~15)**: `wikidb`(28MB) + `dho` DB의 `wiki_chunks`/
  `wiki_page_state`/`wiki_chunk_sync_state`(859MB, 벡터 데이터 대부분)를 `pg_dump -Fc`로
  덤프 → NAS로 전송 → `pg_restore --clean --if-exists`로 복원. NAS의 SFTP 기반 `scp`가
  "No such file or directory"로 실패해서 `scp -O`(레거시 프로토콜)로 우회. `pg_restore`가
  경고성 메시지로 종료코드 1을 반환해 "실패" 알림이 왔지만, 실제 건수(125,328/33,496)와
  HNSW 인덱스까지 정상 복원된 걸 직접 확인 — 알림/종료코드보다 실제 데이터 상태를 우선
  신뢰. NAS `semantic_search_wiki`를 실제 질문("기자 피라미드 던전")으로 재검증, 도구
  호출 → grounded_item 포함 정상 답변 확인.
- 관련 문서(`checklist.md`/`context-notes.md`/`CHANGELOG.md`/`NEXT_STEPS.md`) 전부
  Phase 3 완료로 갱신.

### 결정
- NAS 데이터는 재백필하지 않고 로컬 검증본을 그대로 이관 — 시간(백필 두 배)과 비용
  (임베딩 API 두 배) 모두 절약.
- 도구 관련(중복 호출, 한도) 버그는 시스템 프롬프트 규칙 + 파라미터 조정으로 해결,
  코드 구조 변경은 최소화.

### 해결된 문제
- Wiki.js 동시 쓰기 버그, chat 도구 중복 호출, 로컬 Docker Desktop 다운, 페이지 누적
  타임아웃, NAS scp 프로토콜 문제 — 전부 위 "행동" 항목에 기록된 대로 해결.

### 미해결
- 없음. Phase 3(Wiki.js 배포 + 콘텐츠 생성 + 청크 임베딩) 전체 완료, 로컬/NAS 양쪽
  서빙 준비 끝남.
