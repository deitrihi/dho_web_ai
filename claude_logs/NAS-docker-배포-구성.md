# NAS(원격 서버) Docker 배포 구성

## 요청
- "nas에 있는 docker에 올릴꺼야" — 직전에 만든 chat/ 프론트엔드를 NAS Docker에 배포

## 행동
- `chat/next.config.ts`에 `output: "standalone"` 추가 (Next.js Docker 배포 표준 방식,
  `node_modules/next/dist/docs`의 output.md/self-hosting.md 문서로 확인)
- `chat/Dockerfile` 신규: node:24-alpine 멀티스테이지 빌드(deps → builder → runner).
  `node:sqlite`가 Node 코어 내장 모듈이라 better-sqlite3 같은 네이티브 컴파일 이슈 없이
  깔끔하게 빌드됨. 로컬 Node 버전(v24.15.0)과 맞춰서 이미지도 node:24 사용
- `chat/.dockerignore` 신규: node_modules/.next/.env* 등 제외
- `docker-compose.yml` 재작성: `openwebui` 서비스를 `chat` 서비스(`build: ./chat`)로
  교체. `dbsql/` 폴더 전체를 컨테이너 `/data/dbsql`에 읽기 전용 마운트하고
  `DHO_DB_PATH=/data/dbsql/dho_structured.sqlite3`로 지정 — DB를 이미지에 굽지 않고
  볼륨으로 마운트해서, 나중에 재스테이징해도 컨테이너 재빌드 없이 최신 DB를 그대로
  읽게 함
- `.env.example`의 변수명을 `OPENWEBUI_*` → `OPENAI_*`로 정리 (더 이상 openwebui
  전용이 아니므로)

## 검증
- 로컬 Docker Desktop이 꺼져있어서 PowerShell로 직접 기동, 데몬 준비될 때까지 대기
- `docker compose build chat` — Next.js 빌드(TypeScript 체크 포함) + 이미지 생성까지
  전부 성공
- `docker compose up -d chat`이 포트 3000 충돌로 실패 → 조사해보니 예전
  openwebui/ollama 컨테이너가 3일 전에 생성된 채로 아직 떠 있었음(Docker Desktop
  재시작 시 `restart: unless-stopped` 정책으로 자동 복귀한 것으로 추정). 지금
  docker-compose.yml에는 이 서비스들이 더 이상 정의돼 있지 않아서 고아 컨테이너 상태
- 로컬 검증을 계속하려고 `docker run`으로 포트 3001에 직접 기동 → 페이지 정상 응답,
  `/api/chat`에 플레이스홀더 키로 요청해보니 실제로 OpenAI API까지 요청이 나가서
  401(invalid_api_key) 응답을 받는 것까지 확인 — 배선이 끝까지 정상 동작한다는 뜻
- DB 마운트를 직접 확인하려고 `docker exec`로 sqlite 파일을 열어보려 했는데, Git Bash가
  경로를 `/data/dbsql/...` → `C:/Program Files/Git/data/dbsql/...`로 자동 변환하는
  바람에(MSYS 경로 변환) `docker run -v` 인자 자체가 깨져서 마운트가 아예 안 된 상태였음.
  `MSYS_NO_PATHCONV=1`로 재확인하니 실제 마운트 문제였다는 걸 알았지만, 이건 내가 수동
  `docker run`으로 테스트할 때 셸이 경로를 망가뜨린 것이지 `docker-compose.yml`
  자체의 YAML 마운트 구문(`./:/data/dbsql:ro`) 문제는 아님 — compose는 셸을 거치지
  않고 YAML을 직접 파싱하므로 이 문제가 없음. 실제 배포 환경(NAS의 Linux Docker)에서는
  Git Bash가 개입하지 않으니 문제되지 않을 것으로 판단
- 포트 3000 충돌(고아 컨테이너) 해결 여부를 사용자에게 물어봤더니 "다른 서버에 있는
  docker에 올릴 것"이라는 답변 — 로컬 포트 문제는 실제 배포와 무관하다는 뜻이라 로컬
  컨테이너는 그대로 두고 안 건드림, 정리 작업 대신 배포 절차 문서화로 전환

## 결정
- 로컬 테스트 아티팩트(테스트 컨테이너, 플레이스홀더 `.env`)는 전부 정리하고 실제
  코드/설정 파일만 남김
- 예전 openwebui/ollama 로컬 컨테이너는 사용자가 명시적으로 정리를 요청하기 전까지
  건드리지 않음

## 미해결
- 실제 NAS 서버에 배포해서 진짜 API 키로 end-to-end 테스트 필요 (로컬에서는 배선까지만
  검증, 실제 LLM 응답/도구 호출 체이닝은 미검증)
- 로컬 openwebui/ollama 고아 컨테이너 정리 여부
