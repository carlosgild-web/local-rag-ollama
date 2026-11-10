#!/usr/bin/env bash
# One-command start for macOS and Linux (decision 0013).
#
#   ./start.sh             start (asks a few questions the first time)
#   ./start.sh stop        stop the app (your documents and models are kept)
#   ./start.sh status      show what's running
#
# Options: --yes (accept every suggestion), --check (look and explain, change
# nothing), --reconfigure (ask again instead of using the saved answers).
# Test-only: --no-host-ollama, --no-docker (pretend they're missing).
#
# It never installs anything without asking, only from official sources
# (Homebrew, ollama.com, this repo's GitHub Release with a checksum), and the
# app listens on 127.0.0.1 only. Written for bash 3.2, which macOS ships.

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT/.env"
DATA_DIR="$ROOT/data"
REPO="carlosgild-web/local-rag-ollama"
OLLAMA_URL="http://127.0.0.1:11434"
EMBEDDING_MODEL="bge-m3"
OS="$(uname -s)"

COMMAND="start"; YES=0; CHECK=0; RECONFIGURE=0; NO_HOST_OLLAMA=0; NO_DOCKER=0
for arg in "$@"; do
  case "$arg" in
    start|stop|status) COMMAND="$arg" ;;
    --yes|-y) YES=1 ;;
    --check) CHECK=1 ;;
    --reconfigure) RECONFIGURE=1 ;;
    --no-host-ollama) NO_HOST_OLLAMA=1 ;;
    --no-docker) NO_DOCKER=1 ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)"; exit 2 ;;
  esac
done

# --- Output helpers ----------------------------------------------------------

if [ -t 1 ]; then C_CYAN=$'\033[36m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_OFF=$'\033[0m'
else C_CYAN=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_OFF=""; fi
say()  { printf '%s\n' "$*"; }
step() { printf '\n%s== %s%s\n' "$C_CYAN" "$*" "$C_OFF"; }
ok()   { printf '  %s[ok]%s %s\n' "$C_GREEN" "$C_OFF" "$*"; }
info() { printf '  - %s\n' "$*"; }
warn() { printf '  %s[!]%s %s\n' "$C_YELLOW" "$C_OFF" "$*"; }
fail() { printf '\n%s[x] %s%s\n' "$C_RED" "$*" "$C_OFF"; exit 1; }

# ask "question" [default y|n]: returns 0 for yes
ask() {
  local default="${2:-y}" hint="[Y/n]" answer
  [ "$default" = "n" ] && hint="[y/N]"
  if [ "$YES" = 1 ]; then [ "$default" = "y" ]; return; fi
  printf '  %s %s ' "$1" "$hint"
  read -r answer || answer=""
  [ -z "$answer" ] && answer="$default"
  case "$answer" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

size_of() {
  case "${1%:latest}" in
    bge-m3) echo " (about 1.2 GB)" ;;
    qwen2.5:3b) echo " (about 1.9 GB)" ;;
    llama3.1) echo " (about 4.9 GB)" ;;
    *) echo "" ;;
  esac
}

has() { command -v "$1" >/dev/null 2>&1; }
http_get() { curl -s -m 5 "$1" 2>/dev/null; }

port_free() {
  # Free when nothing accepts a connection on it.
  ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

open_url() {
  if [ "$OS" = "Darwin" ]; then open "$1" >/dev/null 2>&1
  elif has xdg-open; then xdg-open "$1" >/dev/null 2>&1 &
  fi
}

# --- Saved answers (.env, also read by Docker Compose) ---------------------------

START_ROUTE=""; CHAT_MODEL=""; APP_PORT=""
read_settings() {
  [ -f "$ENV_FILE" ] || return 0
  START_ROUTE="$(sed -n 's/^START_ROUTE=//p' "$ENV_FILE" | tail -1)"
  CHAT_MODEL="$(sed -n 's/^CHAT_MODEL=//p' "$ENV_FILE" | tail -1)"
  APP_PORT="$(sed -n 's/^APP_PORT=//p' "$ENV_FILE" | tail -1)"
}
save_settings() {
  {
    echo "# Written by start.cmd / start.sh. Docker Compose reads it too. Safe to delete."
    echo "START_ROUTE=$START_ROUTE"
    echo "CHAT_MODEL=$CHAT_MODEL"
    echo "EMBEDDING_MODEL=$EMBEDDING_MODEL"
    echo "APP_PORT=$APP_PORT"
  } > "$ENV_FILE"
}

compose() {
  # Runs docker compose with the files for the saved route.
  if [ "$START_ROUTE" = "B" ]; then
    (cd "$ROOT" && docker compose -f compose.yaml -f compose.host-ollama.yaml "$@")
  else
    (cd "$ROOT" && docker compose "$@")
  fi
}

# --- Ollama on this computer ---------------------------------------------------

ollama_running() { http_get "$OLLAMA_URL/api/version" | grep -q '"version"'; }
ollama_models() { http_get "$OLLAMA_URL/api/tags" | grep -o '"name":"[^"]*"' | sed 's/"name":"//; s/"$//'; }
is_chat_model() {
  curl -s -m 10 -X POST "$OLLAMA_URL/api/show" -H 'Content-Type: application/json' \
    -d "{\"model\":\"$1\"}" 2>/dev/null | grep -q '"completion"'
}
has_model() {
  local want="$1"
  case "$want" in *:*) ;; *) want="$want:latest" ;; esac
  ollama_models | grep -qx -e "$want" -e "$1"
}

start_host_ollama() {
  info "Ollama is installed but not running; starting it..."
  if [ "$OS" = "Darwin" ] && [ -d /Applications/Ollama.app ]; then open -a Ollama
  else (nohup ollama serve >/dev/null 2>&1 &)
  fi
  local i
  for i in $(seq 1 30); do ollama_running && { ok "Ollama started"; return 0; }; sleep 1; done
  warn "Ollama didn't answer after 30 seconds."
  return 1
}

install_ollama() {
  if [ "$OS" = "Darwin" ]; then
    if has brew; then
      say "  Command: brew install ollama"
      ask "Install Ollama now with Homebrew?" || return 1
      brew install ollama || return 1
    else
      warn "Install Ollama from https://ollama.com/download, then run this again."
      return 1
    fi
  else
    say "  Command: curl -fsSL https://ollama.com/install.sh | sh   (Ollama's official installer; it asks for sudo)"
    ask "Run Ollama's official installer now?" n || return 1
    curl -fsSL https://ollama.com/install.sh | sh || return 1
  fi
  ollama_running || start_host_ollama
}

# --- Docker ----------------------------------------------------------------------

docker_running() { docker info >/dev/null 2>&1; }

start_docker() {
  if [ "$OS" = "Darwin" ]; then
    open -a Docker || return 1
  else
    warn "Start Docker yourself (for example: sudo systemctl start docker), then run this again."
    return 1
  fi
  info "Waiting for Docker Desktop (up to 2 minutes)..."
  local i
  for i in $(seq 1 60); do docker_running && { ok "Docker is running"; return 0; }; sleep 2; done
  warn "Docker didn't start in time."
  return 1
}

# --- Python (route C) -----------------------------------------------------------

PYTHON=""
find_python() {
  local cmd
  for cmd in python3.13 python3.12 python3.11 python3 python; do
    has "$cmd" || continue
    if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PYTHON="$(command -v "$cmd")"; return 0
    fi
  done
  return 1
}

install_python() {
  if [ "$OS" = "Darwin" ] && has brew; then
    say "  Command: brew install python@3.12"
    ask "Install Python 3.12 now with Homebrew?" || return 1
    brew install python@3.12 && find_python
  else
    warn "Install Python 3.11 or newer with your package manager (for example: sudo apt install python3 python3-venv), then run this again."
    return 1
  fi
}

sha256_of() {
  if has sha256sum; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

get_web_app() {
  local dist="$1" base="https://github.com/$REPO/releases/latest/download" tmp
  tmp="$(mktemp -d)"
  info "Downloading the ready-built web app from this project's latest GitHub Release..."
  if curl -fsSL -o "$tmp/web-dist.zip" "$base/web-dist.zip" \
    && curl -fsSL -o "$tmp/web-dist.zip.sha256" "$base/web-dist.zip.sha256" \
    && [ "$(sha256_of "$tmp/web-dist.zip")" = "$(cut -d' ' -f1 < "$tmp/web-dist.zip.sha256" | tr -d '\r\n' | tr 'A-F' 'a-f')" ]; then
    mkdir -p "$dist"
    if has unzip; then unzip -qo "$tmp/web-dist.zip" -d "$dist"
    else "$PYTHON" -m zipfile -e "$tmp/web-dist.zip" "$dist"
    fi
    ok "Web app downloaded and checked (SHA-256)"
  elif has npm; then
    warn "Couldn't download it. Node is installed, so building it here instead."
    (cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build) || fail "The web app build failed."
  else
    rm -rf "$tmp"
    fail "Couldn't get the web app. Check your internet connection, or install Node 22 and run this again."
  fi
  rm -rf "$tmp"
}

setup_route_c() {
  local venv="$ROOT/backend/.venv" req="$ROOT/backend/requirements.txt" marker hash
  if [ ! -x "$venv/bin/python" ]; then
    info "Creating backend/.venv"
    "$PYTHON" -m venv "$venv" || fail "Couldn't create the virtual environment (on Debian/Ubuntu: sudo apt install python3-venv)."
  fi
  marker="$venv/.requirements.sha256"
  hash="$(sha256_of "$req")"
  if [ ! -f "$marker" ] || [ "$(cat "$marker")" != "$hash" ]; then
    info "Installing the Python packages (a few minutes the first time)..."
    "$venv/bin/python" -m pip install --disable-pip-version-check -q -r "$req" || fail "pip install failed; see the messages above."
    echo "$hash" > "$marker"
  fi
  ok "Python packages ready"
  [ -f "$ROOT/frontend/dist/index.html" ] || get_web_app "$ROOT/frontend/dist"
  ok "Web app ready"
}

start_route_c() {
  mkdir -p "$DATA_DIR"
  (
    cd "$ROOT/backend" || exit 1
    DATA_DIR="$DATA_DIR" CHAT_MODEL="$CHAT_MODEL" EMBEDDING_MODEL="$EMBEDDING_MODEL" OLLAMA_BASE_URL="$OLLAMA_URL" \
      nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$APP_PORT" --workers 1 \
      > "$DATA_DIR/server.log" 2>&1 &
    echo $! > "$DATA_DIR/app.pid"
  )
  info "App started in the background (logs: data/server.log)"
}

# --- The app ---------------------------------------------------------------------

wait_healthy() {
  local i body
  info "Waiting for the app to answer..."
  for i in $(seq 1 90); do
    body="$(http_get "http://127.0.0.1:$1/health")"
    if printf '%s' "$body" | grep -q '"status":"ok"'; then ok "All systems OK"; return 0; fi
    if [ -n "$body" ] && [ "$i" -gt 20 ]; then warn "Health: $body"; return 1; fi
    sleep 2
  done
  return 1
}

json_field() { grep -o "\"$1\":[^,}]*" | head -1 | sed "s/\"$1\"://; s/\"//g"; }

load_demo() {
  local port="$1" demo docs status pct last=-1
  demo="$(http_get "http://127.0.0.1:$port/api/demo")"
  printf '%s' "$demo" | grep -q '"available":true' || return 0
  docs="$(printf '%s' "$demo" | json_field documents)"
  if [ "${docs:-0}" != "0" ]; then ok "Your library already has $docs documents"; return 0; fi
  if ! ask "Load the demo company now? (11 documents, a few minutes)"; then
    info "You can load it later from the dashboard."; return 0
  fi
  curl -s -m 10 -X POST "http://127.0.0.1:$port/api/demo/seed" >/dev/null
  while true; do
    sleep 2
    demo="$(http_get "http://127.0.0.1:$port/api/demo")"
    # The job object comes after "job":; its own fields are what we need.
    status="$(printf '%s' "${demo#*\"job\":}" | json_field status)"
    pct="$(printf '%s' "${demo#*\"job\":}" | json_field progress)"
    pct="$(awk -v p="${pct:-0}" 'BEGIN { printf "%d", p * 100 + 0.5 }')"
    [ "$pct" != "$last" ] && { printf '\r  Loading the demo company... %s%%   ' "$pct"; last="$pct"; }
    case "$status" in
      completed) printf '\n'; ok "Demo company loaded"; return 0 ;;
      failed|cancelled) printf '\n'; warn "Loading stopped. Open the dashboard and click Troubleshoot."; return 0 ;;
    esac
  done
}

# --- Commands --------------------------------------------------------------------

do_stop() {
  read_settings
  [ -n "$START_ROUTE" ] || { say "Nothing to stop: start.sh hasn't been run here."; return 0; }
  if [ "$START_ROUTE" = "C" ]; then
    if [ -f "$DATA_DIR/app.pid" ] && kill "$(cat "$DATA_DIR/app.pid")" 2>/dev/null; then ok "App stopped"
    else info "The app wasn't running"; fi
    rm -f "$DATA_DIR/app.pid"
  else
    compose down && ok "App stopped. Your documents and models are kept (docker compose down -v would delete them)."
  fi
}

do_status() {
  read_settings
  [ -n "$START_ROUTE" ] || { say "Not set up yet: run ./start.sh"; return 0; }
  local port="${APP_PORT:-8000}" body
  say "Route $START_ROUTE, chat model $CHAT_MODEL, http://localhost:$port"
  body="$(http_get "http://127.0.0.1:$port/health")"
  if [ -z "$body" ]; then say "The app isn't running."; else say "$body"; fi
}

choose_chat_model() {
  # Sets CHAT_MODEL. $1 = suggested, $2 = 1 when Ollama on this computer can be asked.
  local suggested="$1" chat="" m default="" answer
  if [ "$2" = 1 ]; then
    for m in $(ollama_models); do is_chat_model "$m" && chat="$chat $m"; done
  fi
  if [ -z "$chat" ]; then
    CHAT_MODEL="$suggested"
    if [ "$YES" = 0 ]; then
      printf '  Chat model to use [%s%s]: ' "$suggested" "$(size_of "$suggested")"
      read -r answer || answer=""
      [ -n "$answer" ] && CHAT_MODEL="$answer"
    fi
    return 0
  fi
  for m in $chat; do [ "${m%:latest}" = "$suggested" ] && default="$m"; done
  [ -z "$default" ] && default="$(echo "$chat" | awk '{print $1}')"
  say "  Ollama already has these chat models:$chat"
  CHAT_MODEL="$default"
  if [ "$YES" = 0 ]; then
    printf "  Use %s? Press Enter, or type another name (it's downloaded if missing): " "$default"
    read -r answer || answer=""
    [ -n "$answer" ] && CHAT_MODEL="$answer"
  fi
}

do_start() {
  say ""
  say "Local RAG with Ollama: one-command start"
  say "Everything runs on this computer; your documents never leave it."
  read_settings
  local port="${APP_PORT:-8000}" ram_gb free_gb suggested host_ollama=0 docker_ok=0 route m p

  if [ -n "$START_ROUTE" ] && [ "$CHECK" = 0 ] && [ "$RECONFIGURE" = 0 ] \
    && http_get "http://127.0.0.1:$port/health" | grep -q '"status"'; then
    ok "The app is already running at http://localhost:$port"; open_url "http://localhost:$port/site"; return 0
  fi

  step "1. This computer"
  if [ "$OS" = "Darwin" ]; then ram_gb=$(( $(sysctl -n hw.memsize) / 1073741824 ))
  else ram_gb=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1048576 )); fi
  free_gb=$(( $(df -Pk "$ROOT" | awk 'NR==2 {print $4}') / 1048576 ))
  if [ "$ram_gb" -lt 12 ]; then suggested="qwen2.5:3b"; else suggested="llama3.1"; fi
  info "$OS, about $ram_gb GB of RAM, $free_gb GB free disk"
  info "Suggested chat model: $suggested"
  [ "$free_gb" -lt 8 ] && warn "Less than 8 GB free; the models need 3-7 GB."

  step "2. Ollama and Docker"
  if [ "$NO_HOST_OLLAMA" = 0 ]; then
    if ollama_running; then host_ollama=1; ok "Ollama is running on this computer"
    elif has ollama; then
      if [ "$CHECK" = 1 ]; then info "Ollama is installed but not running (it would be started)"; host_ollama=1
      elif start_host_ollama; then host_ollama=1; fi
    else info "Ollama isn't installed on this computer"; fi
  fi
  if [ "$NO_DOCKER" = 0 ] && has docker; then
    if docker_running; then docker_ok=1; ok "Docker is running"
    elif [ "$CHECK" = 1 ]; then info "Docker is installed but not running (it would offer to start it)"; docker_ok=1
    elif ask "Docker is installed but not running. Start it now?"; then start_docker && docker_ok=1; fi
  elif [ "$NO_DOCKER" = 0 ]; then
    info "Docker isn't installed (optional: https://www.docker.com/products/docker-desktop/)"
  fi

  step "3. How to run it"
  find_python
  if [ -n "$START_ROUTE" ] && [ "$RECONFIGURE" = 0 ]; then
    route="$START_ROUTE"; info "Using your saved choice (route $route). Run with --reconfigure to choose again."
  elif [ "$docker_ok" = 1 ] && [ "$host_ollama" = 1 ] && [ "$OS" = "Darwin" ]; then
    route="B"; info "Route B: the app in Docker, using the Ollama and models already on this computer."
  elif [ "$host_ollama" = 1 ] && [ -n "$PYTHON" ]; then
    # On Linux, Ollama listens on 127.0.0.1 only, so a container can't reach it.
    route="C"; info "Route C: the app runs with Python, next to the Ollama already on this computer."
  elif [ "$docker_ok" = 1 ]; then
    route="A"; info "Route A: the app and Ollama both in Docker; nothing else is installed."
  else
    route="C"; info "Route C: no Docker, so the app runs with Python, next to Ollama on this computer."
  fi

  if [ "$CHECK" = 1 ]; then
    info "Chat model: ${CHAT_MODEL:-$suggested}; embedding model: $EMBEDDING_MODEL"
    say ""; say "--check: nothing was changed."; return 0
  fi

  if [ "$route" = "C" ]; then
    if [ "$host_ollama" = 0 ]; then
      info "Route C needs Ollama on this computer."
      install_ollama || fail "Ollama is needed. Install it from https://ollama.com/download, or install Docker, then run this again."
      host_ollama=1
    fi
    if [ -z "$PYTHON" ]; then
      info "Route C needs Python 3.11 or newer."
      install_python || fail "Python 3.11+ is needed (https://www.python.org/downloads/), or install Docker."
    fi
    ok "Python: $PYTHON"
  fi

  step "4. Models"
  if [ -z "$CHAT_MODEL" ] || [ "$RECONFIGURE" = 1 ]; then
    if [ "$route" = "A" ]; then choose_chat_model "$suggested" 0; else choose_chat_model "$suggested" 1; fi
  fi
  info "Chat model: $CHAT_MODEL; embedding model: $EMBEDDING_MODEL"

  if ! port_free "$port"; then
    for p in 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010; do port_free "$p" && break; done
    port_free "$p" || fail "Ports 8000-8010 are all in use. Free one and run this again."
    warn "Port $port is in use, so the app will use $p."
    port="$p"
  fi
  APP_PORT="$port"; START_ROUTE="$route"
  save_settings

  if [ "$route" != "A" ]; then
    for m in "$EMBEDDING_MODEL" "$CHAT_MODEL"; do
      if has_model "$m"; then ok "$m is already downloaded"
      elif ask "Download $m$(size_of "$m") into Ollama now?"; then ollama pull "$m" || fail "Couldn't download $m."
      else warn "$m isn't downloaded; the app will ask for it."; fi
    done
  fi

  step "5. Starting the app"
  if [ "$route" = "C" ]; then
    setup_route_c
    start_route_c
  else
    info "Starting the containers (the first time downloads the images, which can take a while)..."
    compose pull --quiet app 2>/dev/null || warn "Couldn't check for a newer app image; using the one already downloaded."
    compose up -d || fail "docker compose up failed; see the messages above."
    if [ "$route" = "A" ]; then
      for m in "$EMBEDDING_MODEL" "$CHAT_MODEL"; do
        info "Making sure $m is in Docker's Ollama$(size_of "$m")..."
        compose exec ollama ollama pull "$m" || fail "Couldn't download $m."
      done
    fi
  fi
  wait_healthy "$port" || warn "The app isn't fully healthy yet. Open http://localhost:$port and click Troubleshoot."

  step "6. The demo company"
  load_demo "$port"

  step "Ready"
  say "  Company website:  http://localhost:$port/site"
  say "  Employee portal:  http://localhost:$port/intranet"
  say "  Admin console:    http://localhost:$port"
  say ""
  say "  Stop:    ./start.sh stop      Status: ./start.sh status"
  say "  Your answers are saved in .env; the next start skips the questions."
  open_url "http://localhost:$port/site"
}

case "$COMMAND" in
  stop) do_stop ;;
  status) do_status ;;
  *) do_start ;;
esac
