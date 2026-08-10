#!/usr/bin/env bash
# 이 프로젝트(dbsql/)를 원격 서버(NAS 등)로 전송하고 docker compose로 배포한다.
# 접속 정보는 deploy.config(git에는 안 올라감, deploy.config.example 참고)에서 읽는다.
# 실제 이미지 빌드는 (NAS가 빌드를 감당할 수 있다는 전제로) NAS에서 `docker compose up
# --build`로 하고, 그 전에 로컬에서도 한 번 빌드해봐서 소스 전송 전에 빌드 실패를 걸러낸다.
#
# 사용법
# ------
#   cp deploy.config.example deploy.config   # 최초 1회, 값 채우기
#   ./deploy.sh              # postgres + webapp + chat 전부 배포
#   ./deploy.sh webapp       # webapp만 배포
#   ./deploy.sh chat         # chat만 배포
#
# Windows: Git Bash로 실행한다 (PowerShell에서 `wsl ./deploy.sh`처럼 WSL로 띄우지 않는다).
# WSL은 홈 디렉터리가 Git Bash와 다른 별개 파일시스템이라 DEPLOY_KEY=~/.ssh/... 경로가
# 안 맞아 SSH 키 인증이 깨진다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/deploy.config"
SERVICE="${1:-}"

if [ -n "$SERVICE" ] && [ "$SERVICE" != "webapp" ] && [ "$SERVICE" != "chat" ]; then
  echo "사용법: $0 [webapp|chat]  (인자를 안 주면 전부 배포)" >&2
  exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
  echo "deploy.config가 없습니다. 먼저 아래처럼 만들고 값을 채워주세요:" >&2
  echo "  cp deploy.config.example deploy.config" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${DEPLOY_HOST:?deploy.config에 DEPLOY_HOST를 채워주세요}"
: "${DEPLOY_USER:?deploy.config에 DEPLOY_USER를 채워주세요}"
: "${DEPLOY_PATH:?deploy.config에 DEPLOY_PATH를 채워주세요}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
REMOTE="$DEPLOY_USER@$DEPLOY_HOST"

# 비밀번호 인증은 안 쓴다 — SSH 키(DEPLOY_KEY)로 인증하고, 원격 사용자가 docker
# 그룹에 속해 있다는 전제로 sudo도 안 쓴다. BatchMode=yes라서 키 인증이 안 먹히면
# 비밀번호를 물어보며 멈추는 대신 바로 에러로 실패한다.
SSH_OPTS=(-p "$DEPLOY_PORT" -o BatchMode=yes)
if [ -n "${DEPLOY_KEY:-}" ]; then
  SSH_OPTS+=(-i "$DEPLOY_KEY")
fi

SSH_CMD=(ssh "${SSH_OPTS[@]}")
SSH_CMD_STR="ssh ${SSH_OPTS[*]}"

# 서버에 안 보낼 것들: 빌드/개발 산출물, 원본 HTML 캐시(1.5GB)/구조화 DB(수백MB, 둘 다
# PostgreSQL 이관 이후 서버(webapp/chat)가 더 이상 안 읽음 — 데이터는 migrate_to_postgres.py로
# 별도 이관), 배포 자격증명.
EXCLUDE_PATTERNS=(
  .git
  .claude
  deploy.config
  __pycache__
  "*.pyc"
  dho_cache.sqlite3
  "dho_cache.sqlite3.bak_*"
  dho_structured.sqlite3
  claude_logs
  chat/node_modules
  chat/.next
)

echo "==> 1/4 로컬 빌드 검증 ($([ -n "$SERVICE" ] && echo "$SERVICE" || echo "postgres + webapp + chat"))"
# 실제 배포(빌드)는 NAS에서 하지만, 소스를 전송하기 전에 로컬에서 먼저 빌드해봐서
# 빌드 자체가 깨져 있으면 (전송한 뒤 NAS에서 실패하는 대신) 여기서 바로 걸러낸다.
# docker가 이 셸에서 실제로 안 되면(예: rsync 때문에 WSL로 실행했는데 Docker Desktop WSL
# 통합이 아직 안 붙은 경우) 건너뛴다 — 필수 단계가 아니라 있으면 좋은 사전 검증일 뿐이라
# 배포를 막지 않는다. WSL에서 통합이 안 붙어 있으면 /mnt/c를 통해 보이는 Windows docker.exe가
# "WSL Integration을 켜라"는 안내문을 콘솔에 직접 찍고(stdout/stderr 캡처에 안 잡힘) 종료
# 코드 0으로 끝나버려서, command -v/exit code/출력 캡처 전부로 구분이 안 된다. 대신 진짜
# docker info라면 항상 나오는 "Server Version" 문자열이 캡처됐는지로 판별한다.
DOCKER_PROBE="$(docker info 2>&1)" || true
if command -v docker >/dev/null 2>&1 && echo "$DOCKER_PROBE" | grep -qi "Server Version"; then
  (cd "$SCRIPT_DIR" && docker compose build $SERVICE)
else
  echo "[안내] 이 셸에서 docker가 실제로 동작하지 않아 로컬 빌드 검증을 건너뜁니다 (실제 빌드는 4/4에서 NAS가 함)." >&2
fi

echo "==> 2/4 [$REMOTE:$DEPLOY_PATH] 코드 전송 (dho_cache.sqlite3/dho_structured.sqlite3는 전송 제외)"
"${SSH_CMD[@]}" "$REMOTE" "mkdir -p '$DEPLOY_PATH'"

# 전송 방식 우선순위:
#   1) DEPLOY_RSYNC_TARGET이 설정돼 있으면 rsync 데몬(NAS의 "Rsync 백업 서비스")으로 직접
#      접속 — SSH 세션 위에서 rsync를 돌리는 것보다 안정적이다. 일부 NAS(UGREEN OS 등)는
#      SSH 계정의 로그인 그룹이 admin일 때 자체 rsync 패치가 euid를 root로 못 올려서
#      정상 경로도 "invalid path"로 거부하는 버그가 있는데, 데몬 모드는 이 경로를 아예
#      안 타서 문제가 없다.
#   2) 아니면 로컬에 rsync가 있을 때 기존 SSH 위 rsync (DEPLOY_TRANSFER=tar로 강제 우회 가능)
#   3) 그것도 안 되면 tar (증분 전송 아님)
TRANSFER_MODE="tar"
if [ -n "${DEPLOY_RSYNC_TARGET:-}" ] && command -v rsync >/dev/null 2>&1; then
  TRANSFER_MODE="rsync-daemon"
elif [ "${DEPLOY_TRANSFER:-}" != "tar" ] && command -v rsync >/dev/null 2>&1; then
  TRANSFER_MODE="rsync-ssh"
fi

case "$TRANSFER_MODE" in
  rsync-daemon)
    echo "[안내] rsync 데몬(포트 ${DEPLOY_RSYNC_PORT:-873})으로 전송합니다: $DEPLOY_RSYNC_TARGET" >&2
    RSYNC_EXCLUDES=()
    for p in "${EXCLUDE_PATTERNS[@]}"; do RSYNC_EXCLUDES+=(--exclude "$p"); done
    RSYNC_PASSWORD="${DEPLOY_RSYNC_PASSWORD:?deploy.config에 DEPLOY_RSYNC_PASSWORD를 채워주세요}" rsync -avz --delete --port="${DEPLOY_RSYNC_PORT:-873}" \
      "${RSYNC_EXCLUDES[@]}" "$SCRIPT_DIR/" "$DEPLOY_USER@$DEPLOY_HOST::$DEPLOY_RSYNC_TARGET/"
    ;;
  rsync-ssh)
    RSYNC_EXCLUDES=()
    for p in "${EXCLUDE_PATTERNS[@]}"; do RSYNC_EXCLUDES+=(--exclude "$p"); done
    rsync -avz --delete -e "$SSH_CMD_STR" "${RSYNC_EXCLUDES[@]}" "$SCRIPT_DIR/" "$REMOTE:$DEPLOY_PATH/"
    ;;
  tar)
    echo "[안내] tar로 전송합니다 (증분 전송 아님)." >&2
    TAR_EXCLUDES=()
    for p in "${EXCLUDE_PATTERNS[@]}"; do TAR_EXCLUDES+=(--exclude="$p"); done
    tar czf - "${TAR_EXCLUDES[@]}" -C "$SCRIPT_DIR" . | "${SSH_CMD[@]}" "$REMOTE" "tar xzf - -C '$DEPLOY_PATH'"
    ;;
esac

echo "==> 3/4 .env 확인"
"${SSH_CMD[@]}" "$REMOTE" "test -f '$DEPLOY_PATH/.env' || echo '[경고] $DEPLOY_PATH/.env 가 없습니다 — POSTGRES_*(postgres/webapp/chat)와 OPENAI_*(chat) 키 설정이 있어야 동작합니다 (.env.example 참고).'"

echo "==> 4/4 docker compose 빌드 + 기동 ($([ -n "$SERVICE" ] && echo "$SERVICE" || echo "postgres + webapp + chat"))"
"${SSH_CMD[@]}" "$REMOTE" "cd '$DEPLOY_PATH' && docker compose up -d --build $SERVICE"

echo "완료. 로그 확인: ssh -p $DEPLOY_PORT $REMOTE \"cd $DEPLOY_PATH && docker compose logs -f $SERVICE\""
