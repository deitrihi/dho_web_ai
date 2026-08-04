# CHANGELOG

## [미커밋]

## 2026-08-04 | 77f86c6

- deploy.bat — 신규: `& "C:\Program Files\Git\bin\bash.exe" ./deploy.sh` 타이핑이 번거롭다는
  피드백으로 더블클릭 실행용 런처 추가(인자 그대로 전달, Git Bash 미설치 시 안내 후 종료,
  종료 후 pause로 결과 확인 가능). 한글 주석/echo 문구를 넣었더니 cmd.exe가 UTF-8 멀티바이트
  줄을 파싱하다 다음 줄 앞부분까지 깨뜨리는 문제 발견(BOM 추가, `chcp 65001` 둘 다 시도했지만
  재현됨) — batch 파일 자체는 ASCII만 쓰도록 전부 영어로 작성해 해결. `deploy.bat webapp`
  실제 실행으로 전송→빌드→기동까지 정상 동작 확인(컨테이너 `Running`)
- deploy.sh — `dho_structured.sqlite3`를 전송 제외 목록에 추가. webapp의 항목 추가/수정
  기능으로 서버 쪽 DB가 로컬보다 최신일 수 있어서, 배포할 때마다 로컬(구버전)로 덮어써버리는
  사고를 막음. rsync는 --exclude된 파일을 비교 대상에서 빼서 --delete로도 안 건드리고, tar는
  아카이브에 없는 파일이라 추출 시 서버 파일이 그대로 유지됨(두 전송 모드 모두 안전).
  관련 안내 메시지/주석도 함께 정리
- deploy.sh, deploy.config.example — 비밀번호 인증(sshpass)/원격 `sudo docker compose`를
  SSH 키 인증(`DEPLOY_KEY`) + 원격 사용자를 docker 그룹에 넣는 방식으로 교체. 사용자가 겪던
  "docker build가 deploy에서 처리 안 돼서 매번 직접 SSH로 들어가서 처리" 문제의 원인은 두
  가지였음 — (1) sshpass 미설치라 ssh가 물어볼 때마다 수동 입력 필요, (2) 최근 추가된
  `sudo docker compose`가 pty 없는 원격 세션에서 실행돼 sudo 비밀번호를 못 받고 조용히
  실패. NAS(`deitrihi@192.168.0.200`)에 전용 키(`~/.ssh/id_ed25519_nas`) 등록 +
  `usermod -aG docker deitrihi`로 sudo 없이 docker 접근 가능하게 만든 뒤 `./deploy.sh`
  실행으로 비밀번호 프롬프트 0회, 전송→빌드→기동까지 한 번에 끝나는 것 실제 확인
  (webapp/chat 컨테이너 정상 기동). `deploy.config`의 평문 `DEPLOY_PASSWORD`도 제거
  (rsync 데몬 인증용 `DEPLOY_RSYNC_PASSWORD`만 별도 유지, SSH 인증과는 무관)
- deploy.sh — 사용자가 `wsl ./deploy.sh`로 실행하다 `DEPLOY_KEY=~/.ssh/...`를 못 찾는 오류 발견
  (WSL 홈 디렉터리가 Git Bash와 별개 파일시스템). WSL의 rsync로 DB(245MB) 증분 전송하려던
  용도였는데, 같은 LAN이라 Git Bash의 tar 전체 전송도 충분히 빨라 WSL 없이 Git Bash로만
  실행하기로 결정 — 스크립트 상단에 안내 주석 추가
- chat/app/components/rich-content.tsx(신규), chat/app/page.tsx, chat/package.json — 챗봇
  응답이 항상 raw 텍스트(`<span>`)로만 나오던 문제 수정. 시스템 프롬프트는 "표/목록을
  활용해서" 답하라고 지시하는데 프론트는 마크다운을 파싱 안 해서 `| 이름 | 값 |` 같은
  원문이 그대로 보였음. `react-markdown`+`remark-gfm`(표/취소선 등 GFM)+`remark-breaks`
  (마크다운 미사용 응답도 기존처럼 단일 줄바꿈 유지)로 텍스트 파트를 렌더링하도록 교체.
  tool 호출 파트도 `JSON.stringify` 한 줄 표시 대신 `<details>`로 접어두고(스트리밍 중엔
  접힘, 완료 시 자동 펼침), 결과가 배열-of-객체면 표로, 객체면 key-value 목록으로 재귀
  렌더링하는 `JsonValue` 컴포넌트로 교체(list_categories/get_item_detail/run_sql 등 6개
  도구 결과 전부 공통 처리). `npm run build`/`npm run lint` 통과, dev 서버로 페이지 200
  렌더링 확인(실제 LLM 응답 스트리밍은 API 키 미설정 환경이라 미검증)
- chat/app/api/chat/route.ts, chat/app/page.tsx — 실사용 중 발견: 도구 호출이 많이 필요한
  질문("포술을 얻을 수 있는 NPC 위치/이름")에서 `stopWhen: stepCountIs(8)`에 정확히
  걸려(스크린샷에 도구 호출 8개) 최종 답변 텍스트를 생성할 스텝 없이 스트림이 그냥
  끝나버리는 버그 수정 — 사용자에게는 아무 응답 없이 "멈춘" 것처럼 보였음. 스텝 한도를
  16으로 상향. 앞으로도 한도에 걸릴 가능성은 남아있어, 마지막 assistant 메시지가 텍스트
  파트 없이 끝나면(스트리밍 종료 후) "도구 호출 한도 도달" 경고 문구를 표시하도록
  `page.tsx`에 fallback 추가
- deploy.sh — 1/4 로컬 빌드 검증 단계를 docker가 실제로 동작할 때만 실행하도록 수정.
  WSL로 실행할 때(rsync 때문에 필요) Docker Desktop WSL 통합이 안 붙어 있으면 `/mnt/c`를
  통해 보이는 Windows docker.exe가 "WSL Integration을 켜라"는 안내문을 콘솔에 직접 찍고
  종료 코드 0으로 끝나버려서(stdout/stderr 캡처로 안 잡힘) `command -v`/exit code로는 구분이
  안 됐음 — `docker info` 출력에 "Server Version" 문자열이 실제로 캡처되는지로 판별하도록
  변경, Git Bash(정상)/WSL(통합 안 됨) 양쪽에서 직접 확인. 이 단계는 필수가 아니라 사전
  검증용이라 안 되면 그냥 건너뛰고 4/4(NAS에서 빌드)로 진행됨
- deploy.sh, deploy.config.example — rsync 데몬(NAS의 "Rsync 백업 서비스") 전송 모드 추가.
  SSH 위에서 rsync를 돌리는 기존 방식은 UGREEN OS에서 admin 그룹 계정의 euid 상승 실패로
  "invalid path" 오류가 나는 걸 확인했는데(DEPLOY_TRANSFER=tar로 우회 가능하게 해뒀던 문제),
  NAS의 Rsync 백업 서비스(데몬, 포트 873)를 켜고 `DEPLOY_RSYNC_TARGET`(모듈/하위경로,
  예: `docker/dho_dbsql`)을 설정하면 이 경로를 아예 안 타서 문제없이 동작하는 것을 실제
  NAS에 대고 읽기/쓰기/삭제까지 직접 확인함. 전송 방식 우선순위를 rsync 데몬 → SSH 위
  rsync → tar 순으로 정리(`DEPLOY_RSYNC_TARGET` > `DEPLOY_TRANSFER` > 자동판별).
  `DEPLOY_RSYNC_PASSWORD`(데몬 비밀번호가 DEPLOY_PASSWORD와 다를 때만)도 추가
- dho_webapp.py, templates/base.html, templates/chat.html(신규), static/style.css — 왼쪽 사이드바
  하단에 "chat.ai" 메뉴 추가. `/assistant` 라우트가 base.html 레이아웃(사이드바 유지) 안에
  `<iframe src="{{ chat_url }}">`로 챗봇을 임베드. wrapper 라우트 경로를 `/chat`으로
  시작하지 않게 잡은 이유: 운영 환경에서는 nginx가 외부 도메인 443 하나로 들어온 요청을
  `/`→webapp:5050, `/chat`→chat:3000로 나눠 프록시해주는데, `location /chat`은 접두어
  매칭이라 `/chat-ai`처럼 "chat"으로 시작하는 경로는 전부 그 규칙에 걸려서 chat
  컨테이너(3000)로 잘못 넘어가 버림(webapp까지 요청이 오지도 못하고 chat 쪽에 없는
  라우트라 404). 게다가 nginx 없이 webapp에 직접 붙었을 땐 `/<category>` 캐치올 라우트가
  먼저 "chat"을 존재하지 않는 카테고리로 처리해 또 다른 404를 냄(사용자가 애초에 겪은
  버그 원인). 두 문제를 한 번에 피하려고 wrapper 경로를 아예 `/assistant`로 정함
  (처음엔 `/chat-ai`로 했다가 nginx 접두어 충돌로 404 재발 확인 후 변경).
  iframe 대상 주소는 `DHO_CHAT_URL` 환경변수로 지정(기본값 `/chat` — nginx가 같은
  origin에서 알아서 chat 컨테이너로 넘겨주므로 브라우저가 포트를 몰라도 됨. nginx 없이
  webapp을 직접 접속해서 테스트할 때만 `DHO_CHAT_URL=http://<host>:3000/chat`처럼
  절대경로로 오버라이드)
- deploy.sh — 소스 전송 전에 로컬에서 `docker compose build`로 먼저 빌드해보는 단계(1/4) 추가.
  실제 이미지 빌드는 그대로 NAS에서 `docker compose up --build`로 하지만(사용자가 그 방식을
  선택), 256MB 넘는 DB까지 전송한 뒤 NAS에서 빌드가 깨진 걸 알게 되는 상황을 막으려고 로컬
  사전 검증만 추가. bash -n 문법 확인 + 가짜 호스트로 전체 흐름(빌드 성공 → 전송 단계에서
  의도적으로 실패)까지 실행해서 빌드 실패 시 이후 단계로 안 넘어가는 것 확인
- deploy.config.example — `DEPLOY_PATH` 기본값을 실제 NAS 경로(`/volume1/docker/dho_dbsql`)로
  갱신, ControlMaster 제거 반영 안 됐던 비밀번호 관련 주석도 같이 수정
- chat/next.config.ts, chat/app/page.tsx, chat/Dockerfile, docker-compose.yml — nginx가 chat을
  `/chat` 서브패스로 프록시할 때 404 나던 문제 수정. 원인은 Next.js `basePath` 미설정 —
  nginx는 `/chat` 접두어를 안 벗기고 그대로 전달하는데(`proxy_pass http://host:3000;`, URI
  없음), 앱은 자기가 루트(`/`)에 떠 있다고 생각해서 `/chat/*` 경로에 매칭되는 라우트가 없어
  전부 404였음. `next.config.ts`에 빌드타임 `NEXT_BASE_PATH` 환경변수로 `basePath` 설정
  (안 주면 빈 값 — 로컬 `npm run dev`는 그대로 루트에서 동작), `NEXT_PUBLIC_BASE_PATH`로
  클라이언트에도 노출. `app/page.tsx`의 `useChat` API 경로(`/api/chat`)도 이 값으로 접두어를
  붙이도록 수정 — basePath는 next/link 등 Next.js 자체 기능에만 자동 적용되고 수동 fetch
  경로는 직접 붙여줘야 함. `Dockerfile`은 `ARG NEXT_BASE_PATH`를 받아 빌드 시 주입,
  `docker-compose.yml`의 chat 서비스에 `build.args: NEXT_BASE_PATH=/chat` 추가. 로컬에서
  이미지 재빌드 후 컨테이너로 `/`(404, 의도됨) `/chat`(200) `/chat/api/chat`(200) `/chat/_next/
  static/...` 에셋 경로까지 전부 컨테이너 레벨에서 직접 확인 완료
- deploy.sh — ControlMaster/ControlPersist(ssh 연결 재사용) 제거. 실사용 중 Windows의 ssh
  포트에서 `mux_client_request_session: read from master failed: Connection reset by peer`로
  깨지는 것 확인 — 비밀번호를 한 번만 물어보게 하려던 최적화였는데 안정성이 더 중요해서
  제거. 이제 비밀번호 인증 + sshpass 미설치 시 단계별로 여러 번 물어볼 수 있음
- deploy.sh, deploy.config.example — 신규: 원격 서버(NAS)로 프로젝트를 전송하고
  `docker compose up -d --build`까지 자동으로 실행하는 배포 스크립트. SSH 접속 정보(주소/
  계정/비밀번호/원격 경로)는 git에 안 올라가는 `deploy.config`(예시는 `deploy.config.example`)
  에서 읽음. 비밀번호 인증 시 `sshpass`가 있으면 자동 입력, 없으면 ssh가 직접 물어보되
  ControlMaster로 연결을 재사용해서 배포 1회당 한 번만 묻게 함. 전송은 `rsync`가 있으면
  우선 사용(증분 전송), 없으면 `tar | ssh` 파이프로 대체. `dho_cache.sqlite3`(1.5GB, 배포에
  안 씀)/`chat/node_modules`/`__pycache__` 등은 전송 제외 목록에 포함. `deploy.config` 없이
  실행 시 안내 메시지 + 종료, 필수 값 누락 시 어떤 값이 비었는지 알려주도록 검증 로직 확인함
  (실제 서버 접속까지는 미검증 — 로컬에서 문법 검사와 exclude 패턴 동작만 확인)
- .gitignore — `deploy.config` 추가 (SSH 자격증명이라 커밋되면 안 됨)
- Dockerfile, requirements.txt, .dockerignore — 신규: dho_webapp.py 배포용. python:3.13-slim +
  gunicorn(2 workers)으로 구동, DB(dho_structured.sqlite3)는 이미지에 안 담고 볼륨 마운트
  (이미지 크기/재빌드 부담 줄이려고 chat/Dockerfile과 같은 방침). 로컬에서 `docker build` +
  `docker run`으로 실제 컨테이너 기동, 페이지 렌더링, 항목 생성(쓰기) 전부 확인 완료
  (테스트 데이터는 정리함)
- dho_webapp.py — `DB_PATH`를 `DHO_DB_PATH` 환경변수로 오버라이드 가능하게 변경(기존 기본값은
  그대로 유지). chat/ 컨테이너와 동일한 관례
- docker-compose.yml — `webapp` 서비스 추가: `dho_structured.sqlite3`를 컨테이너에 읽기-쓰기로
  단일 파일 마운트(항목 추가/수정 기능이 DB에 직접 쓰므로 chat 서비스와 달리 read-only 아님),
  5050 포트로 노출. 상단 설명 주석을 webapp+chat 두 서비스를 함께 설명하도록 갱신
- dho_webapp.py — 항목 추가/수정 기능 신규: `/<category>/new`(생성), `/<category>/<item_id>/edit`
  (수정) GET/POST 라우트 추가. 조회용 `get_db()`(읽기 전용)와 별개로 `get_write_db()`를 추가해서
  쓰기 요청에서만 씀. 사용자가 추가한 항목은 `item_id`를 900000000부터 순번 할당(원본 재크롤링과
  안 겹치게). 속성은 라벨/값 반복 입력, 표는 탭으로 구분된 텍스트(엑셀 복붙 가능)를 첫 줄=헤더로
  파싱해서 저장 — 링크/이미지 편집은 범위 밖(v1)
- templates/item_form.html — 신규: 항목 생성/수정 폼. 속성/표 행을 JS(`<template>` + clone)로
  동적 추가/삭제
- templates/category.html, templates/item.html — "새 항목 추가"/"수정" 버튼 추가
- static/style.css — 폼 스타일(`.item-form`, `.form-row`, `.form-table-block`,
  `.btn-add-row`/`.btn-remove-row`/`.btn-primary` 등) 추가
- static/style.css — 표 색상 대비 개선: `--table-border`/`--table-head-bg`를 표 전용 변수로
  분리(기존 `--border`는 사이드바/카드 등에 계속 쓰이므로 유지). 다크모드에서 테두리/헤더 배경이
  카드 배경과 거의 구분 안 되던 문제 수정, `th` 글자색도 `--muted` → `--fg`로 변경
- static/style.css — `.table-scroll`에 `white-space: normal` 추가. 부모 `.row-value`의
  `white-space: pre-wrap`이 상속되면서 `<table>` 앞뒤의 템플릿 들여쓰기 공백이 빈 줄로
  렌더링되던 버그 수정 (표 있는 행 위아래로 2줄씩 여백이 생기던 문제)
- templates/item.html — `.row-value` 안 `{% if %}`/`{% else %}`/`{% endif %}` 경계에 Jinja
  공백 제거 문법(`{%-`, `{{-`, `-%}`) 추가. `trim_blocks`/`lstrip_blocks`는 `{% %}` 블록에만
  적용되고 `{{ }}` 출력 태그는 안 건드려서, 속성 값 앞에 줄바꿈+들여쓰기가 그대로 남아
  라벨과 값이 위아래로 떨어져 보이던 버그 수정
- static/style.css — `.row` 패딩 `9px 0` → `7px 0`, 표 `line-height`/셀 패딩 축소로 목록
  줄 간격을 전반적으로 조밀하게 조정
- dho_webapp.py, templates/item.html — `with_links` Jinja 필터 신규: 셀 텍스트 안에서 링크에
  해당하는 부분을 실제 `<a>`로 치환해서 렌더링. 기존엔 텍스트 전체(get_text() 결과, 링크 텍스트
  포함)와 링크 목록을 따로 렌더링해서 같은 내용이 줄만 바뀌어 중복 표시되던 버그 수정
- static/style.css — `.main-col`에 `min-height: 0` 추가. grid item의 기본 `min-height: auto`
  때문에 `main`의 `overflow-y: auto`가 실제로는 동작 안 하고 `.shell`의 `overflow: hidden`이
  넘치는 내용을 그냥 잘라버리던 버그 수정 (본문 스크롤이 전혀 안 되던 문제)

- chat/ — 신규 서브프로젝트: OpenWebUI를 대체하는 Vercel AI SDK 기반 Text-to-SQL 챗봇
  프론트엔드 (Next.js App Router). `openwebui_tool_dho_sql.py`의 6개 Tool 함수를
  `chat/lib/dho-db.ts`로 포팅(Node.js 내장 `node:sqlite`로 `dho_structured.sqlite3`
  읽기 전용 접근). `chat/app/api/chat/route.ts`(streamText + stepCountIs(8) 멀티스텝
  도구 호출), `chat/app/page.tsx`(다크 테마 채팅 UI). `chat/.env.local.example`,
  `chat/README.md` 추가. 기존 openwebui_tool_dho_sql.py는 삭제 안 하고 그대로 둠
- chat/Dockerfile, chat/.dockerignore, chat/next.config.ts — 신규/수정: Next.js
  `output: "standalone"` + node:24-alpine 멀티스테이지 빌드로 원격(NAS) 배포용 이미지
  구성. 로컬에서 `docker compose build chat` 빌드 성공 + 컨테이너 기동 + 실제 OpenAI API
  엔드포인트까지 요청 도달(플레이스홀더 키라 401 응답으로 배선 확인, 실응답은 미검증)
  까지 확인
- docker-compose.yml — openwebui 서비스를 chat 서비스(`build: ./chat`)로 교체.
  `dbsql/` 폴더 전체를 컨테이너에 읽기 전용 마운트(`DHO_DB_PATH`로 경로 지정),
  `OPENAI_API_BASE_URL`/`OPENAI_API_KEY`/`OPENAI_MODEL` 환경변수 사용
- .env.example — `OPENWEBUI_*` 변수명을 `OPENAI_*`로 변경(더 이상 openwebui 전용이
  아니므로)
- chat/README.md — NAS 등 원격 서버로의 Docker 배포 절차(rsync로 프로젝트 전송 →
  .env 준비 → `docker compose up -d --build chat`) 추가
- chat/app/api/chat/route.ts — `createOpenAI()` 호출을 모듈 최상단에서 POST 핸들러
  내부로 이동. Next.js 빌드가 모듈 최상단의 `process.env.OPENAI_API_BASE_URL`을
  빌드 타임(값 없음)에 인라인해버려서, 컨테이너 실행 시 docker-compose가 넣어주는
  런타임 환경변수를 계속 무시하고 `AI_InvalidArgumentError: baseURL must be a
  non-empty string`가 나던 버그 수정. NAS 실배포 중 발견(모든 질문이 스트리밍 없이
  바로 500)
- Synology NAS(`/volume1/docker/dho_chat`) 실배포 완료. 배포 과정에서 발견된 이슈:
  robocopy `/XD`가 `chat\node_modules`처럼 백슬래시 포함 경로를 못 매칭해서
  node_modules/.next/.git이 잘못 복사됨(NAS에서 삭제로 해결), NAS에 이미 있던
  구버전 `.env`(`OPENWEBUI_*` 변수명, 실제 키 포함)를 `OPENAI_*`로 현지에서 변수명만
  치환, Windows SMB로 복사된 `dho_structured.sqlite3`를 컨테이너 비루트 사용자가
  못 읽던 권한 문제(`chmod -R a+rX`로 해결— 향후 재동기화 시 재발 가능, 매번 재실행
  필요)
- build_backlinks.py — 신규: raw_attrs.links_json/raw_tables 셀 링크를 전부 스캔해서
  정방향 링크(이 항목 -> 다른 항목)를 뒤집은 `item_backlinks` 인덱스 테이블 생성
  (440,926건, 중복 제거 후). "이 항목을 참조하는 곳" 백링크 섹션의 데이터 소스
- dho_webapp.py — `get_backlinks()` 추가: 소스 카테고리별로 묶어 뱃지(개수)+목록 형태로
  반환, 카테고리당 최대 30건만 노출하고 나머지는 "OO 외 N건 더"로 표시(흔한 항목은
  backlink가 최대 6,468건까지 있음). `item_detail()`에 연결
- templates/item.html, static/style.css — 백링크 섹션(뱃지 + 2단 그리드 목록) 추가.
  Jinja 템플릿에서 dict 키를 "items"로 쓰면 `dict.items()` 내장 메서드와 충돌해 렌더링이
  깨지는 걸 발견 → "entries"로 변경
- dho_webapp.py — `get_list_columns()` 추가: raw_attrs에서 카테고리별 속성 라벨의 평균
  글자 수를 계산해 짧고(≤20자) 분류값스러운 속성만 최대 7개까지 카테고리 목록 표의
  컬럼으로 자동 선정(장문 속성은 자연히 제외). `category_list()`를 이름 목록에서
  라벨-값 피벗 데이터 표로 재작성, 컬럼 값이 전부 숫자면 정렬 시 `CAST(...AS INTEGER)`로
  진짜 숫자 정렬. `sort`/`dir` 쿼리 파라미터로 컬럼 클릭 정렬 지원(파라미터는 실제 컬럼
  라벨 화이트리스트와 대조 후에만 SQL에 사용 — 인젝션 방지). 속성 컬럼이 없는 카테고리는
  기존 단순 이름 목록으로 자동 폴백
- templates/category.html, static/style.css — 통계 컬럼 표 + 정렬 가능한 헤더(▲▼ 표시)
  렌더링 추가
- build_structured_db.py — `parse_cell()`의 `get_text("\n", strip=True)`가 인라인 링크/툴팁
  경계마다 텍스트 조각을 strip 후 "\n"으로 이어붙이면서 원본 공백을 잃고 표 셀이 줄바꿈
  투성이로 깨지던 버그 수정. 구분자 없는 `get_text().strip()`으로 교체 (원본 텍스트 노드가
  이미 필요한 공백을 포함하고 있어 그대로 이어붙이면 원본과 동일하게 읽힘)
- dho_structured.sqlite3 — 위 수정 반영해 전체 재스테이징(`build_structured_db.py stage`) +
  `build_acquisition.py` + `materialize_*.py` 전체 재실행
- dho_webapp.py — `get_nav_groups()`/`get_group_title()` 추가, `context_processor`로
  전체 페이지에 사이드바 내비게이션 데이터 주입, `item_detail()`에 `category` 변수 누락
  수정(사이드바 활성 카테고리 표시가 상세 페이지에서 동작 안 하던 버그)
- templates/base.html — 원본 사이트 레이아웃(좌측 대분류 사이드바 + 상단 헤더바 +
  브레드크럼 바)에 대응하는 셸 구조로 재작성, 색상은 기존 다크/라이트 팔레트 그대로 유지
- templates/item.html — 카드 섹션 + 2단 속성 그리드 + 라운드보더 표로 재작성
- templates/item.html, static/style.css — 사용자 요청으로 속성 영역을 2단 그리드에서
  단일 컬럼 리스트(라벨-값 한 줄씩)로 재변경. 속성/표를 `.row-list` 하나로 통합해서
  같은 라벨 폭(120px)으로 정렬되도록 함 (`.attr-grid`/`.attr-row`/`.table-block` 계열
  클래스 제거, `.row-list`/`.row`/`.row-label`/`.row-value`로 교체)
- templates/category.html — 카드 스타일 컨테이너로 재구성 (정렬/필터 없는 단순 목록 유지,
  원본처럼 카테고리별 통계 컬럼 표는 범위 밖으로 보류)
- templates/index.html — 대분류 그룹을 카드 스타일로 재구성
- build_structured_db.py — SCHEMA_VERSION 3. `raw_attrs`에 `images_json`/`position`,
  `raw_tables`에 `position` 컬럼 추가.
  1) `parse_cell()`이 `<figure><img>+<figcaption>`(퀘스트 "이미지" 행 등)을 텍스트로
     흡수해서 "이미지" 속성값에 캡션 글자("공략" 등)가 잘못 들어가던 버그 수정 — figure를
     먼저 뽑아서 `images` 리스트에 담고 트리에서 제거한 뒤 나머지 텍스트를 추출하도록 변경
  2) `extract_detail()`이 attrs/tables를 별도 리스트로 나누면서 원본 문서상의 상대 순서를
     잃던 문제 수정 — 순회 중 순번(`position`)을 매겨서 저장, 나중에 다시 합칠 때 원본과
     같은 순서로 복원 가능하게 함
- dho_webapp.py — `item_detail()`을 `attrs`/`tables` 두 리스트 대신 `position` 기준으로
  병합한 단일 `rows` 리스트를 넘기도록 재작성 (표가 항상 속성 뒤로 밀려나던 문제 해결)
- templates/item.html — `rows`를 순서대로 순회하며 attr/table 타입별로 분기 렌더링,
  attr에 이미지가 있으면 `<figure><img></figure>`로 표시하도록 추가
- static/style.css — `.row-images`/`.row-images img` 등 이미지 표시 스타일 추가
- dho_structured.sqlite3 — 위 스키마 변경 반영해 전체 재스테이징 +
  `build_acquisition.py` + `materialize_*.py` 전체 재실행
- 전체 33,496건 상세 페이지를 Flask test_client로 스모크 테스트(500 에러 0건 확인) +
  라벨 길이/표 헤더 개수/이미지 개수 등 극단값 데이터로 시각 검증하면서 아래 3개
  이슈 추가 발견 및 수정.
  1) `static/style.css` — `body`에 `word-break: keep-all` 추가. 좁은 라벨 컬럼(속성
     라벨 120px 등)에서 긴 한글 라벨이 "오른쪽" → "오"+"른쪽"처럼 음절 중간에서
     줄바꿈되던 문제 수정. `overflow-wrap: break-word`는 표 셀의 auto layout이 짧은
     내용("소비품" 등)까지 과도하게 좁혀서 줄바꿈시키는 부작용이 있어 같이 넣지 않음
  2) `build_structured_db.py` — 표 셀 안에 중첩 `<table>`이 들어있는 경우(discovery
     "논전 콤보"/"장식품"의 발견물 카드 목록, quest "필요"의 선행 스킬 목록 등, 총
     1,345건 영향) `table.find_all("tr")`/`tr.find_all("td")`가 재귀 탐색이라 중첩 표의
     행/셀까지 같이 주워서 헤더-셀 개수가 안 맞거나 중첩 표의 행이 바깥 표의 행인 것처럼
     잘못 섞여 들어가던 버그 수정. `tbody`의 직계 `tr`, `tr`의 직계 `td`만 골라서 중첩
     표는 건드리지 않도록 스코프 제한. `parse_cell()`에는 중첩 표를 ", "로 이어붙인
     인라인 텍스트로 펼치는 로직 추가(원본 소스가 셀 사이 공백 없이 붙어있어서 그냥
     get_text()하면 "카르타고 유적한니발대리석상..."처럼 이어져버림). 링크는 유지되어
     그대로 클릭 가능. 수정 후 헤더-셀 개수 불일치 2,721건 → 0건 확인
  3) `static/style.css`의 `.row-value`에 `white-space: pre-wrap` 추가 — 속성 값에
     원본이 의도한 개행이 있는 경우(예: "연결 지도/퀘스트"에 여러 퀘스트 후보가 나열될
     때) 지금까진 개행이 공백으로 뭉개져서 여러 항목이 구분 없이 붙어 보였음. 이 CSS를
     추가하니 예전에 `.links`에서 겪었던 것과 같은 계열의 문제가 재발 — Jinja 템플릿의
     `{% if %}`/`{% for %}` 블록 사이 들여쓰기 공백이 pre-wrap 때문에 그대로 렌더링되어
     속성값마다 빈 줄이 잔뜩 생김. 이번엔 CSS로 땜빵하는 대신 근본 원인을 고침 —
     `dho_webapp.py`에 `app.jinja_env.trim_blocks = True` / `lstrip_blocks = True` 설정
     추가해서 템플릿 블록 태그 주변 공백이 애초에 렌더링 결과에 안 남게 함
- 위 3개 수정 반영해 전체 재스테이징 + `build_acquisition.py` + `materialize_*.py`
  재실행, 전체 33,496건 재스모크테스트로 최종 확인(500 에러 0건)
- static/style.css — 사이드바/헤더바/브레드크럼/카드/속성그리드/표 스타일 전면 추가.
  `.links`가 `<td>`의 `white-space: pre-wrap`을 상속해 링크마다 줄바꿈되던 버그 발견해
  `white-space: normal` 추가로 수정
- docker-compose.yml — NAS 이전 대비: GPU 필요한 ollama 서비스 제거, openwebui가 외부
  AI API(OpenAI 호환 엔드포인트)를 쓰도록 OPENAI_API_BASE_URL/OPENAI_API_KEY 환경변수 추가
  (.env에서 로드), ollama named volume 제거
- docker-compose.yml — DEFAULT_MODELS 환경변수 추가, 기본 모델 gpt-5-mini로 지정
- .env.example — 신규: API 엔드포인트/키/기본 모델(gpt-5-mini) 값 채워 넣는 템플릿
- .gitignore — 신규: .env(API 키) 커밋 방지
- scraper.py — `get_max_page()`, `crawl_category_list()`에서 `category` 값을 정규식에 삽입할 때 `re.escape()` 적용 (regex injection 방지)
- NEXT_STEPS.md — 참고 ERD 없음을 반영, 원본 사이트 구조 기반 스키마 설계로 문구 수정
- NEXT_STEPS.md — 전체 크롤링 완료 상태 반영
- scraper.py — `fetch()`에서 응답 인코딩을 `utf-8`로 명시 (서버가 charset 미명시 → requests가
  ISO-8859-1로 오판하던 문제 수정)
- dho_cache.sqlite3 — `pages.html` 전체(34,198건) latin1→utf8 라운드트립으로 복구,
  `categories`/`items`를 복구된 캐시로부터 재파싱하여 갱신 (백업: dho_cache.sqlite3.bak_before_encoding_fix)
- plan.md, checklist.md, context-notes.md — 2단계(구조화 DB) 계획 문서 신규 작성
- build_structured_db.py — 신규: 원본 HTML → 범용 {title,description,attrs,tables} 추출 후
  dho_structured.sqlite3에 스테이징(items_core/raw_attrs/raw_tables) 적재, 전체 33,496건 처리
- build_acquisition.py — 신규: 카테고리 공유 "획득 방법/변성연금/종류-내용" 관계 테이블
  (item_detail_list, item_transmutation_*, item_acquisition_*) 생성 및 적재
- materialize_cannon.py — 신규: cannon 카테고리 전용 테이블 파일럿 구현 및 검증 (566건)
- build_acquisition.py — item_acquisition_directsale(판매기간/수량/가격) 매핑 추가
- materialize_recipe.py — 신규: recipe 전용 테이블 (recipe_product) 구현 및 검증 (3,045건)
- materialize_consumable.py — 신규: consumable 전용 테이블 구현 및 검증 (2,510건)
- materialize_tarotcard.py — 신규: tarotCard 전용 테이블 구현 및 검증 (22건)
- build_acquisition.py — COVERED_HEADER_SHAPES 상수 export (범용 스크립트가 재사용)
- materialize_generic.py — 신규: 나머지 66개 카테고리를 자동으로 전용 테이블화
  (한글 라벨을 컬럼명으로 사용, 숫자/링크 자동판별). 전체 70/70 카테고리 완료,
  ship/equipment/city 샘플 대조 검증 통과. dho_structured.sqlite3 총 211개 테이블
- docker-compose.yml — 신규: ollama+openwebui를 docker run 개별 관리에서 compose로 전환,
  dbsql 프로젝트 폴더를 openwebui 컨테이너에 읽기 전용(`/data/dbsql`)으로 마운트
  (2단계 Text-to-SQL Tool에서 dho_structured.sqlite3 접근용). 기존 named volume은
  external로 재사용해 모델/채팅 기록 유지
- openwebui_tool_dho_sql.py — 신규: OpenWebUI Tool. list_categories/find_tables/
  get_table_schema/run_sql 4개 함수로 211개 테이블을 단계적으로 탐색해 Text-to-SQL 수행.
  read-only 커넥션(mode=ro) + SELECT 전용 + 세미콜론 인젝션 차단으로 안전장치.
  실제 DB 대상 스모크 테스트 통과 (list_categories/find_tables/get_table_schema/run_sql
  정상 동작, DROP TABLE 및 `SELECT 1; DROP TABLE` 둘 다 차단 확인)
- ollama qwen2.5:7b 모델 신규 pull — 기존 exaone3.5:7.8b는 tools capability 없어서
  Tool 호출 불가 확인, qwen2.5:7b는 tools capability 확인됨 (12GB VRAM 여유롭게 수용)
- openwebui_tool_dho_sql.py — `search_items(keyword)` 함수 추가. 실사용 테스트("준사관으로
  전직하면 우대 스킬") 중 발견: "준사관" 같은 고유명사는 테이블 이름이 아니라 items_core의
  데이터 값(category=job)이라 find_tables로는 못 찾는 문제 확인, search_items로 items_core.
  name/title을 직접 검색하도록 보완. job 테이블 "우대 스킬" 컬럼까지 조회되는 것 검증 완료
- openwebui_tool_dho_sql.py — `get_item_detail(keyword)` 함수 추가. 실사용 테스트 중 발견:
  qwen2.5:7b가 search_items로 category=job/item_id=2492를 정확히 찾고도 다음 단계
  (get_table_schema→run_sql)로 못 이어가고 컬럼명("우대 스킬")을 또 다른 아이템 이름처럼
  재검색하다 실패 → 로컬 소형 모델은 여러 단계 도구 체이닝이 약함을 확인. 이름 검색+상세
  조회를 한 번에 처리하는 get_item_detail을 1순위 함수로 추가해 체이닝 의존성 제거,
  준사관/job 케이스로 단일 호출 검증 완료
- scrape_hidden_tabs.py — 신규: 실사용 질문("해양조합 등록증 해상 NPC 획득") 중 발견한
  스크래핑 누락 버그 수정. 사이트의 "획득 방법" 섹션이 탭 UI(퀘스트/아이템 사용/해상 NPC 등)로
  되어 있는데, 기존 scraper.py(순수 HTTP)는 클라이언트 사이드 탭 전환으로만 렌더링되는 표를
  캡처 못함 — 원본 HTML엔 탭 버튼 라벨만 있고 비활성 탭의 표 데이터는 아예 없음(라이브 사이트
  직접 재확인으로 캐시 문제 아님을 확인). 전수 스캔 결과 33,496건 중 3,365건(약 10%,
  consumable/equipment/tradeGoods/field/city/sea/cannon 등에 집중) 영향 확인.
  Playwright로 해당 항목만 탭을 실제로 클릭해서 새 표/속성을 raw_tables/raw_attrs에 추가
  삽입(기존 행 유지, hidden_tabs_progress 테이블로 재실행 시 이어서 진행 가능). 10건 테스트로
  해상 NPC 표(`해상 NPC/함대 수/해역` — build_acquisition.py에 이미 매핑 코드 있었음) 및
  cannon의 숨겨진 레시피 책 획득 경로까지 정상 추가되는 것 검증. 첫 실행이 특정 항목에서
  hang(CPU 사용량 0인 채 수 시간 정체)되어 프로세스 강제 종료 후 재시작 — 개별 항목 45초
  하드 데드라인, Playwright 기본 타임아웃 10초, 200건마다 page 재생성으로 보강. 전체
  3,365건 완주(오류 0건, 1,210건에서 신규 데이터 발견)
- build_acquisition.py, materialize_generic.py, materialize_consumable.py,
  materialize_cannon.py — scrape_hidden_tabs.py로 추가된 raw_tables 반영 위해 재실행.
  item_acquisition_marine_npc 4,352행, item_acquisition_marine_npc_sea 5,980행으로 갱신.
  해양조합 등록증(item_id=1898) 해상 NPC 78건 정상 반영 확인 — 최초 버그 리포트 케이스 해결
- openwebui_tool_dho_sql.py — `get_item_detail`에 `_acquisition_info()` 헬퍼 추가. gpt-5-mini로
  재테스트 중 발견: DB 수정은 끝났는데도 모델이 certificate 전용 테이블만 뒤지고
  item_acquisition_marine_npc_sea 같은 공유 관계 테이블은 못 찾아서 여전히 "없다"고 오답 —
  카테고리 전용 테이블과 공유 획득처 테이블(item_acquisition_*/item_transmutation_*)이
  분리돼 있어서 모델이 멀티테이블 조인을 스스로 알아내야 하는 구조적 문제였음. get_item_detail
  결과에 "획득_방법" 필드로 관련 공유 테이블을 category+item_id 기준 자동 조인해서 통째로
  반환하도록 변경, 모델이 추가 쿼리 없이 한 번에 볼 수 있게 함. 해양조합 등록증 케이스로
  검증(marine_npc 77건 NPC명/함대수 포함, marine_npc_sea 78건, from_item 7건까지 한 번에 반환)
- dho_webapp.py, templates/, static/style.css — 신규: 원본 사이트와 동일한 정보 구조(카테고리
  목록 → 항목 목록 → 상세: 속성+표)를 보여주는 Flask 조회 전용 웹앱. items_core/raw_attrs/
  raw_tables가 원본 페이지를 1:1로 옮겨온 스테이징 데이터라(scrape_hidden_tabs.py 보강분
  포함) 이 세 테이블만으로 렌더링 — 디자인은 원본 CSS를 따라하지 않고 간결하게 새로 작성.
  같은 label의 표가 여러 개면("획득 방법" 등) 첫 헤더로 구분되는 이름을 자동으로 붙임(예:
  "획득 방법 — 해상 NPC"). 로컬 실행(:5050)으로 certificate/1898 상세 페이지 렌더링,
  marineNpc/sea 카테고리로의 상호 링크 이동, 존재하지 않는 카테고리 404 처리까지 검증 완료
- build_category_localization.py — 신규: 웹앱에서 카테고리가 영문 slug("cannon")로만 보이고
  원본 사이트의 6개 대분류(모험/아이템/선박/인물 · 스킬/NPC/세계) 그룹핑도 없다는 피드백으로
  발견. DB 자체엔 대분류 정보가 없어서, 원본 사이트가 배포하는 정적 JS 번들
  (`/assets/categories-*.js`)에 카테고리 한글명(`bt`)과 대분류 매핑(`xt`)이 그대로 하드코딩돼
  있는 것을 확인하고 그 값을 그대로 옮겨옴. 원본 데이터를 건드리지 않는 별도 로컬라이제이션
  테이블 `category_localization`(slug, label_ko, group_title_ko, group_flag, group_order,
  order_in_group)으로 신규 생성 — dho_structured.sqlite3의 실제 category 70개와 전수 대조해서
  누락/불일치 0건 확인. dho_webapp.py가 이 테이블을 조인해서 홈 화면 대분류 그룹핑 + 카테고리/
  브레드크럼 한글 표시에 반영하도록 수정, cannon(대포)/certificate(추천장) 페이지로 검증 완료
