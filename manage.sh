#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$PROJECT_DIR/.runtime"
LOG_DIR="$RUN_DIR/logs"
TOOLS_DIR="$PROJECT_DIR/.tools"
FRONTEND_DIR="$PROJECT_DIR/frontend"

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8100}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

cd "$PROJECT_DIR"
mkdir -p "$RUN_DIR" "$LOG_DIR" "$TOOLS_DIR"

find_uv() {
  if [[ -x "$TOOLS_DIR/uv" ]]; then
    printf '%s\n' "$TOOLS_DIR/uv"
  elif command -v uv >/dev/null 2>&1; then
    command -v uv
  else
    return 1
  fi
}

install_runtime() {
  local uv_bin
  if ! uv_bin="$(find_uv)"; then
    echo "[install] Installing uv into $TOOLS_DIR"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$TOOLS_DIR" sh
    uv_bin="$TOOLS_DIR/uv"
  fi

  echo "[install] Preparing Python $PYTHON_VERSION and backend dependencies"
  "$uv_bin" python install "$PYTHON_VERSION"
  "$uv_bin" sync --frozen --python "$PYTHON_VERSION"

  echo "[install] Applying PostgreSQL migrations"
  "$PROJECT_DIR/.venv/bin/alembic" upgrade head

  echo "[install] Installing and building frontend"
  (
    cd "$FRONTEND_DIR"
    npm ci
    NEXT_PUBLIC_API_URL=/api BACKEND_URL="http://127.0.0.1:$API_PORT" npm run build
  )
  echo "[install] Complete"
}

pid_alive() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file")"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

port_busy() {
  local port="$1"
  ss -ltn | awk '{print $4}' | grep -Eq "(^|:)$port$"
}

start_service() {
  local name="$1"
  shift
  local pid_file="$RUN_DIR/$name.pid"
  local log_file="$LOG_DIR/$name.log"

  if pid_alive "$pid_file"; then
    echo "[start] $name already running (PID $(cat "$pid_file"))"
    return
  fi
  rm -f "$pid_file"
  nohup setsid "$@" >>"$log_file" 2>&1 &
  local pid=$!
  echo "$pid" >"$pid_file"
  sleep 1
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "[start] $name failed; see $log_file"
    tail -n 40 "$log_file" || true
    return 1
  fi
  echo "[start] $name started (PID $pid)"
}

start_all() {
  if [[ ! -x "$PROJECT_DIR/.venv/bin/uvicorn" || ! -d "$FRONTEND_DIR/node_modules" || ! -d "$FRONTEND_DIR/dist" ]]; then
    install_runtime
  fi
  if port_busy "$API_PORT" && ! pid_alive "$RUN_DIR/api.pid"; then
    echo "[start] API port $API_PORT is already occupied"
    return 1
  fi
  if port_busy "$FRONTEND_PORT" && ! pid_alive "$RUN_DIR/frontend.pid"; then
    echo "[start] Frontend port $FRONTEND_PORT is already occupied"
    return 1
  fi

  start_service api env PYTHONUNBUFFERED=1 \
    "$PROJECT_DIR/.venv/bin/uvicorn" mediaforge.gateway.main:app \
    --host "$API_HOST" --port "$API_PORT"
  start_service worker env PYTHONUNBUFFERED=1 \
    "$PROJECT_DIR/.venv/bin/celery" -A mediaforge.celery_app worker \
    -Q high,normal,low -l info
  start_service beat env PYTHONUNBUFFERED=1 \
    "$PROJECT_DIR/.venv/bin/celery" -A mediaforge.celery_app beat \
    -l info --schedule "$RUN_DIR/celerybeat-schedule"
  start_service frontend env BACKEND_URL="http://127.0.0.1:$API_PORT" \
    npm --prefix "$FRONTEND_DIR" run start -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT"

  echo "[start] Waiting for API readiness"
  local ready=0
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$API_PORT/ready" >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 2
  done
  if [[ "$ready" -ne 1 ]]; then
    echo "[start] API did not become ready; see $LOG_DIR/api.log"
    return 1
  fi
  echo "[start] MediaForge ready: frontend=$FRONTEND_PORT api=$API_PORT"
}

stop_service() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"
  if ! pid_alive "$pid_file"; then
    rm -f "$pid_file"
    echo "[stop] $name is not running"
    return
  fi
  local pid
  pid="$(cat "$pid_file")"
  kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 15); do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$pid_file"
      echo "[stop] $name stopped"
      return
    fi
    sleep 1
  done
  kill -9 -- "-$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
  rm -f "$pid_file"
  echo "[stop] $name force-stopped"
}

stop_all() {
  stop_service frontend
  stop_service beat
  stop_service worker
  stop_service api
}

status_all() {
  local name
  for name in api worker beat frontend; do
    if pid_alive "$RUN_DIR/$name.pid"; then
      echo "$name: running (PID $(cat "$RUN_DIR/$name.pid"))"
    else
      echo "$name: stopped"
    fi
  done
  if curl -fsS "http://127.0.0.1:$API_PORT/ready" >/dev/null 2>&1; then
    echo "api readiness: ok"
  else
    echo "api readiness: unavailable"
  fi
}

show_logs() {
  local name="${1:-api}"
  tail -n 100 -f "$LOG_DIR/$name.log"
}

case "${1:-}" in
  install) install_runtime ;;
  start) start_all ;;
  stop) stop_all ;;
  restart) stop_all; start_all ;;
  status) status_all ;;
  logs) show_logs "${2:-api}" ;;
  *)
    echo "Usage: $0 {install|start|stop|restart|status|logs [api|worker|beat|frontend]}"
    exit 1
    ;;
esac
