# 노션 데이터 챗봇 검색 연동 — 컨텍스트 노트

## 요구사항 확정 과정
사용자에게 4라운드에 걸쳐 확인한 결과:
- 데이터 방향: 노션 → 로컬 SQLite (반대 방향 아님)
- 대상: 여러 페이지(문서 형태), 상위 페이지 1개 + 하위 페이지 전체
- 저장 위치: 기존 `dho_structured.sqlite3`에 새 테이블로 (별도 DB 파일 아님)
- 연동 방식: Python 스크립트 1회성이 아니라 주기적 동기화(스케줄러)
- 주기: 하루 1번
- 인증 토큰: 이미 발급받아 `.env`의 `NOTION_API_KEY`에 저장해둠
- 상위 페이지: https://app.notion.com/p/deitrihi-screte/9f16031c9d82446cb9f851eb4b235be8
  (페이지 ID: `9f16031c9d82446cb9f851eb4b235be8`)

## 왜 items_fts에 안 섞고 별도 테이블인가
사용자가 직접 "게임 정보 vs 개인 메모, 성격이 다르면 분리가 나을 수 있다"는 질문에
"같은 DB에 새 테이블로 추가"를 선택 — 같은 DB 파일은 유지하되 테이블/인덱스는 분리하는
절충안으로 이해하고 진행.

## Notion MCP 커넥터 관련
이 세션 시작 시 `notion` MCP 서버가 인증 안 된 상태였음 — Claude Code가 직접 노션을
조회하는 방식(MCP)이 아니라, REST API를 호출하는 Python 스크립트를 작성하는 방식으로 진행.
사용자가 나중에 `/mcp`로 노션 MCP를 인증하면 대화 중 직접 노션을 조회하는 것도 가능해지지만,
이번 동기화 스크립트는 그것과 무관하게 독립적으로 동작함(스크립트는 MCP를 거치지 않고
Notion REST API를 직접 호출).

## 페이지 텍스트 추출 방식
Notion 블록 트리를 재귀 순회하며 각 블록 타입의 `rich_text`를 plain_text로 이어붙임.
`child_page` 타입 블록을 만나면 그 블록 id가 곧 하위 페이지의 page_id이므로 별도로
`fetch_page()`를 재귀 호출 — 이런 식으로 상위 페이지 아래 트리 전체를 수집.

## 진행 중 발견 사항

### 로컬 `python -c` 출력의 한글 mojibake는 표시 문제였음 (실제 데이터 정상)
`python -c "..."`로 Git Bash stdout에 직접 print한 한글이 깨져 보여서 처음엔 저장
데이터 자체가 깨졌나 의심했으나, 파일로 UTF-8 덤프해서 Read 툴로 확인하니 DB에는
정상적으로 저장돼 있었음 — Git Bash 콘솔 코드페이지 표시 문제일 뿐, 실제 인코딩 버그
아님. `dho_cache.sqlite3`의 과거 mojibake 이슈([[encoding_bug_fixed]] 메모리 참고)와는
무관.

### NAS가 실제 운영 환경이라 배포 방식을 재설계함
로컬 동기화 완료 후 사용자가 "NAS에 배포된 DB가 있는데 webapp 등에서 DB에 데이터를
변경하고 있다"고 알려줌 — `deploy-bat-런처-및-db-배포-제외.md` 로그를 확인해보니
`deploy.sh`가 `dho_structured.sqlite3`를 이미 의도적으로 배포 제외 중(NAS가 최신
데이터를 갖고 있다는 전제). 이 때문에:
- 로컬에서 돌린 `sync_notion.py`는 로컬 사본에만 반영됨, NAS DB는 그대로.
- NAS 웹앱 컨테이너에는 `requests`도, `sync_notion.py`도 없어서 단순 파일 복사로는
  안 돌아감.
- 사용자 확인 결과 NAS가 주 사용처 → Windows 작업 스케줄러 계획을 폐기하고, 대신
  `notion-sync`라는 별도 docker-compose 서비스를 만들어 컨테이너 내부에서
  `sleep 86400` 루프로 하루 1회 반복 실행하는 방식으로 전환. NAS OS(브랜드마다 다른
  Task Scheduler UI)에 의존하지 않기 위한 선택.
- 컨테이너는 webapp과 동일하게 `dho_structured.sqlite3`를 읽기-쓰기로 마운트 —
  NAS의 "최신 DB"에 새 테이블(`notion_pages`/`notion_fts`)만 추가하는 것이라 webapp이
  쓰는 기존 데이터와 충돌 없음.

### 부수적으로 발견한 문제 → 사용자 요청으로 수정함
`Dockerfile`(webapp용)에 `build_search_index.py`가 `COPY` 목록에 빠져 있던 문제.
`dho_webapp.py`의 `DERIVED_PIPELINE_SCRIPTS`는 항목 저장마다 이 스크립트도 실행하려
시도하는데, NAS 컨테이너엔 파일이 없어 매번 조용히 실패(`rebuild_derived_tables()`는
실패를 `errors` 리스트로만 모으고 계속 진행)했을 가능성이 높음 — 즉 NAS의 `items_fts`가
새 항목 저장 후에도 최신 데이터로 재생성되지 않고 있었을 수 있음.
`COPY` 목록에 `build_search_index.py` 추가로 수정. `build_search_index.py`는
`os`/`sqlite3`/`pathlib`만 쓰는 stdlib 스크립트라 `requirements.txt` 변경은 불필요.
`DERIVED_PIPELINE_SCRIPTS` 8개 스크립트 전부를 `COPY` 목록과 대조해서 다른 누락은
없음을 확인.

### 로컬 Docker 데몬 미가동으로 빌드 검증 못 함
`docker compose build notion-sync`를 시도했으나 이 PC의 Docker 데몬이 꺼져 있어 실패
(`deploy.sh` 자체도 이 상황을 감지하면 로컬 빌드 검증을 건너뛰도록 이미 설계돼 있음).
YAML(`docker compose config`)과 셸 스크립트 문법(`bash -n`)은 검증했지만, 실제 이미지
빌드는 사용자가 `./deploy.sh` 실행 시 NAS에서 처음 확인됨.
