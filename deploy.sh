#!/usr/bin/env bash
# 이 프로젝트(dbsql/)를 원격 서버(NAS 등)로 전송하고 docker compose로 배포한다.
# 접속 정보는 deploy.config(git에는 안 올라감, deploy.config.example 참고)에서 읽는다.
# 실제 이미지 빌드는 (NAS가 빌드를 감당할 수 있다는 전제로) NAS에서 `docker compose up
# --build`로 하고, 그 전에 로컬에서도 한 번 빌드해봐서 소스 전송 전에 빌드 실패를 걸러낸다.
#
# 사용법
# ------
#   cp deploy.config.example deploy.config   # 최초 1회, 값 채우기
#   ./deploy.sh              # webapp + chat 둘 다 배포
#   ./deploy.sh webapp       # webapp만 배포
#   ./deploy.sh chat         # chat만 배포
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/deploy.config"
SERVICE="${1:-}"

if [ -n "$SERVICE" ] && [ "$SERVICE" != "webapp" ] && [ "$SERVICE" != "chat" ]; then
  echo "사용법: $0 [webapp|chat]  (인자를 안 주면 둘 다 배포)" >&2
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

SSH_OPTS=(-p "$DEPLOY_PORT")

SSH_CMD=(ssh "${SSH_OPTS[@]}")
SSH_CMD_STR="ssh ${SSH_OPTS[*]}"
if [ -n "${DEPLOY_PASSWORD:-}" ]; then
  if command -v sshpass >/dev/null 2>&1; then
    SSH_CMD=(sshpass -p "$DEPLOY_PASSWORD" ssh "${SSH_OPTS[@]}")
    SSH_CMD_STR="sshpass -p $DEPLOY_PASSWORD ssh ${SSH_OPTS[*]}"
  else
    echo "[안내] sshpass가 없어서 비밀번호를 자동으로 넣지 못합니다. ssh가 물어볼 때마다(전송/확인/배포 단계별로 여러 번) 직접 입력해주세요." >&2
  fi
fi

# 서버에 안 보낼 것들: 빌드/개발 산출물, 원본 HTML 캐시(1.5GB, 배포엔 안 씀), 배포 자격증명
EXCLUDE_PATTERNS=(
  .git
  .claude
  deploy.config
  __pycache__
  "*.pyc"
  dho_cache.sqlite3
  "dho_cache.sqlite3.bak_*"
  claude_logs
  chat/node_modules
  chat/.next
)

echo "==> 1/4 로컬 빌드 검증 ($([ -n "$SERVICE" ] && echo "$SERVICE" || echo "webapp + chat"))"
# 실제 배포(빌드)는 NAS에서 하지만, 소스를 전송하기 전에 로컬에서 먼저 빌드해봐서
# 빌드 자체가 깨져 있으면 (256MB짜리 DB까지 전송한 뒤 NAS에서 실패하는 대신) 여기서 바로 걸러낸다.
(cd "$SCRIPT_DIR" && docker compose build $SERVICE)

echo "==> 2/4 [$REMOTE:$DEPLOY_PATH] 코드 + DB 전송"
"${SSH_CMD[@]}" "$REMOTE" "mkdir -p '$DEPLOY_PATH'"

if command -v rsync >/dev/null 2>&1; then
  RSYNC_EXCLUDES=()
  for p in "${EXCLUDE_PATTERNS[@]}"; do RSYNC_EXCLUDES+=(--exclude "$p"); done
  rsync -avz --delete -e "$SSH_CMD_STR" "${RSYNC_EXCLUDES[@]}" "$SCRIPT_DIR/" "$REMOTE:$DEPLOY_PATH/"
else
  echo "[안내] rsync가 없어서 tar로 전송합니다 (증분 전송이 아니라 dho_structured.sqlite3 때문에 시간이 걸릴 수 있음)." >&2
  TAR_EXCLUDES=()
  for p in "${EXCLUDE_PATTERNS[@]}"; do TAR_EXCLUDES+=(--exclude="$p"); done
  tar czf - "${TAR_EXCLUDES[@]}" -C "$SCRIPT_DIR" . | "${SSH_CMD[@]}" "$REMOTE" "tar xzf - -C '$DEPLOY_PATH'"
fi

echo "==> 3/4 .env 확인"
"${SSH_CMD[@]}" "$REMOTE" "test -f '$DEPLOY_PATH/.env' || echo '[경고] $DEPLOY_PATH/.env 가 없습니다 — chat 서비스는 OPENAI_* 키 설정이 있어야 동작합니다 (.env.example 참고).'"

echo "==> 4/4 docker compose 빌드 + 기동 ($([ -n "$SERVICE" ] && echo "$SERVICE" || echo "webapp + chat"))"
"${SSH_CMD[@]}" "$REMOTE" "cd '$DEPLOY_PATH' && docker compose up -d --build $SERVICE"

echo "완료. 로그 확인: ssh -p $DEPLOY_PORT $REMOTE \"cd $DEPLOY_PATH && docker compose logs -f $SERVICE\""
