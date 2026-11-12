#!/usr/bin/env bash
# One-command start for macOS and Linux (decision 0013).
#
#   ./start.sh             start (asks a few questions the first time)
#   ./start.sh stop        stop the app (your documents and models are kept)
#   ./start.sh status      show how it's running and whether it's healthy
#   ./start.sh backup      back up the data now (the console's Backups page too)
#   ./start.sh restore <backup>   restore a backup (a name from Backups, or a .zip file)
#
# Options: --yes (accept every suggestion), --check (look and explain, change
# nothing), --reconfigure (ask again instead of using the saved answers).
# Test-only: --no-host-ollama, --no-docker (pretend they're missing),
# --ollama-start-fails (pretend Ollama won't start).
#
# It never installs anything or falls back to another way without asking, only
# installs from official sources (Homebrew, ollama.com, this repo's GitHub
# Release with a checksum), and the app listens on 127.0.0.1 only. Each run is
# logged to data/start.log. Written for bash 3.2, which macOS ships.

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$ROOT/.env"
DATA_DIR="$ROOT/data"
LOG_FILE="$DATA_DIR/start.log"
REPO="carlosgild-web/local-rag-ollama"
OLLAMA_URL="http://127.0.0.1:11434"
EMBEDDING_MODEL="bge-m3"
OS="$(uname -s)"
LOGGING=0
OLLAMA_STARTED_HERE=0

COMMAND="start"; TARGET=""; YES=0; CHECK=0; RECONFIGURE=0; NO_HOST_OLLAMA=0; NO_DOCKER=0; OLLAMA_START_FAILS=0
for arg in "$@"; do
  case "$arg" in
    start|stop|status|backup|restore) COMMAND="$arg" ;;
    --yes|-y) YES=1 ;;
    --check) CHECK=1 ;;
    --reconfigure) RECONFIGURE=1 ;;
    --no-host-ollama) NO_HOST_OLLAMA=1 ;;
    --no-docker) NO_DOCKER=1 ;;
    --ollama-start-fails) OLLAMA_START_FAILS=1 ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "Unknown option: $arg (try --help)"; exit 2 ;;
    *)
      if [ "$COMMAND" = "restore" ] && [ -z "$TARGET" ]; then TARGET="$arg"
      else echo "Unknown option: $arg (try --help)"; exit 2; fi ;;
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
fail() {
  printf '\n%s[x] %s%s\n' "$C_RED" "$*" "$C_OFF"
  [ "$LOGGING" = 1 ] && printf '    Details of this run: data/start.log\n'
  exit 1
}
quit() { printf '\n%s\n' "$*"; exit 0; }

# prompt_line "text": prints the question, reads one line into ANSWER. With piped
# answers (tests, CI) it echoes the answer, so the log shows both.
ANSWER=""
prompt_line() {
  printf '%s ' "$1"
  ANSWER=""
  IFS= read -r ANSWER || ANSWER=""
  [ -t 0 ] || printf '%s\n' "$ANSWER"
}

# ask "question" [default y|n]: returns 0 for yes
ask() {
  local default="${2:-y}" hint="[Y/n]"
  [ "$default" = "n" ] && hint="[y/N]"
  if [ "$YES" = 1 ]; then [ "$default" = "y" ]; return; fi
  prompt_line "  $1 $hint"
  [ -z "$ANSWER" ] && ANSWER="$default"
  case "$ANSWER" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

# choose "question" LETTERS DEFAULT: sets CHOICE to one upper-case letter
CHOICE=""
choose() {
  local letters="$2"
  CHOICE="$3"
  [ "$YES" = 1 ] && return 0
  while true; do
    prompt_line "  $1 [$3]"
    [ -z "$ANSWER" ] && { CHOICE="$3"; return 0; }
    CHOICE="$(printf '%s' "$ANSWER" | cut -c1 | tr '[:lower:]' '[:upper:]')"
    case "$letters" in *"$CHOICE"*) return 0 ;; esac
    say "  Please type one of: $(printf '%s' "$letters" | sed 's/./&, /g; s/, $//')"
  done
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

# compose ROUTE args...: docker compose with the files for that route
compose() {
  local route="$1"; shift
  if [ "$route" = "B" ]; then
    (cd "$ROOT" && docker compose -f compose.yaml -f compose.host-ollama.yaml "$@")
  else
    (cd "$ROOT" && docker compose "$@")
  fi
}

container_names() { compose "$1" ps --format '{{.Name}}' 2>/dev/null | tr '\n' ' ' | sed 's/ $//'; }

describe_route() {
  case "$1" in
    A) echo "in Docker (route A): the app and Ollama both run in containers" ;;
    B) echo "in Docker (route B): the app runs in a container and uses the Ollama on this computer" ;;
    *) echo "with Python, without Docker (route C), next to the Ollama on this computer" ;;
  esac
}

# --- Ollama on this computer ---------------------------------------------------

ollama_running() { http_get "$OLLAMA_URL/api/version" | grep -q '"version"'; }
ollama_state() {
  if [ "$NO_HOST_OLLAMA" = 1 ]; then echo missing
  elif ollama_running; then echo running
  elif has ollama || [ -d /Applications/Ollama.app ]; then echo stopped
  else echo missing; fi
}
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
  # The normal way for each system: the app on macOS, the service on Linux.
  if [ "$OLLAMA_START_FAILS" = 1 ]; then info "(test) pretending Ollama won't start"; sleep 2; return 1; fi
  if [ "$OS" = "Darwin" ] && [ -d /Applications/Ollama.app ]; then
    info "Starting the Ollama app..."; open -a Ollama
  elif [ "$OS" = "Linux" ] && has systemctl && systemctl list-unit-files ollama.service 2>/dev/null | grep -q '^ollama'; then
    # A user-level `ollama serve` couldn't see the service's models, so start the service.
    say "  Command: sudo systemctl start ollama"
    if ask "Start Ollama's system service now (it asks for your password)?"; then sudo systemctl start ollama || return 1
    else return 1; fi
  else
    info "Starting ollama serve in the background..."; (nohup ollama serve >/dev/null 2>&1 &)
  fi
  local i
  for i in $(seq 1 60); do ollama_running && { OLLAMA_STARTED_HERE=1; ok "Ollama started"; return 0; }; sleep 1; done
  return 1
}

# ensure_host_ollama OFFER_DOCKER: sets OLLAMA_RESULT to "running" or "docker"
OLLAMA_RESULT=""
ensure_host_ollama() {
  local attempt=0
  info "Ollama is installed but not running."
  while true; do
    attempt=$((attempt + 1))
    if start_host_ollama; then OLLAMA_RESULT="running"; return 0; fi
    warn "Ollama didn't answer within 60 seconds."
    [ "$YES" = 1 ] && [ "$attempt" -ge 2 ] && fail "Ollama didn't start. Start it yourself, then run this again."
    if [ "$1" = 1 ]; then
      choose "[R]etry, use Ollama inside [D]ocker instead (downloads the models again, about 3 GB), or [Q]uit?" "RDQ" "R"
    else
      choose "[R]etry or [Q]uit?" "RQ" "R"
    fi
    [ "$CHOICE" = "Q" ] && quit "Stopped; nothing was changed. Start Ollama yourself, then run this again."
    [ "$CHOICE" = "D" ] && { OLLAMA_RESULT="docker"; return 0; }
  done
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
  ollama_running && return 0
  ensure_host_ollama 0
  [ "$OLLAMA_RESULT" = "running" ]
}

# --- Docker ----------------------------------------------------------------------

DOCKER_STATE=""; DOCKER_DETAIL=""
docker_state() {
  local out
  if [ "$NO_DOCKER" = 1 ] || ! has docker; then DOCKER_STATE="missing"; DOCKER_DETAIL=""; return; fi
  if out="$(docker info --format '{{.ServerVersion}}' 2>&1)"; then DOCKER_STATE="running"; DOCKER_DETAIL="$out"
  else DOCKER_STATE="down"; DOCKER_DETAIL="$(printf '%s' "$out" | grep -v '^[[:space:]]*$' | tail -2 | tr '\n' ' ')"; fi
}

wait_docker() {
  if [ "$OS" = "Darwin" ]; then
    info "Starting Docker Desktop..."; open -a Docker >/dev/null 2>&1 || warn "Couldn't open Docker Desktop; start it yourself, and this keeps waiting."
  elif has systemctl && systemctl --user list-unit-files docker-desktop.service 2>/dev/null | grep -q '^docker-desktop'; then
    info "Starting Docker Desktop..."; systemctl --user start docker-desktop
  elif has systemctl && systemctl list-unit-files docker.service 2>/dev/null | grep -q '^docker'; then
    say "  Command: sudo systemctl start docker"
    ask "Start Docker's system service now (it asks for your password)?" && sudo systemctl start docker
  fi
  info "Waiting for Docker to answer (up to 3 minutes)..."
  local i
  for i in $(seq 1 90); do
    docker_state; [ "$DOCKER_STATE" = "running" ] && { ok "Docker is running"; return 0; }
    sleep 2
  done
  warn "Docker still isn't answering."
  return 1
}

# ensure_docker OFFER_PYTHON: sets DOCKER_RESULT to "running" or "python"
DOCKER_RESULT=""
ensure_docker() {
  warn "Docker is installed but isn't answering${DOCKER_DETAIL:+: $DOCKER_DETAIL}"
  while true; do
    if [ "$1" = 1 ]; then
      choose "[W]ait for Docker (starts Docker if it's closed), use [P]ython instead, or [Q]uit?" "WPQ" "W"
    else
      choose "[W]ait for Docker (starts Docker if it's closed), or [Q]uit?" "WQ" "W"
    fi
    [ "$CHOICE" = "Q" ] && quit "Stopped; nothing was changed. Start Docker, then run this again."
    [ "$CHOICE" = "P" ] && { DOCKER_RESULT="python"; return 0; }
    wait_docker && { DOCKER_RESULT="running"; return 0; }
    [ "$YES" = 1 ] && fail "Docker didn't answer within 3 minutes. Start Docker, then run this again (or run with --reconfigure and choose Python)."
  done
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
      > "$DATA_DIR/server.log" 2>&1 < /dev/null &
    echo $! > "$DATA_DIR/app.pid"
  )
  info "App started in the background (logs: data/server.log)"
}

# Downloads a model into Docker's Ollama; on failure explains and offers Retry/Quit.
pull_in_docker() {
  local attempt=0
  while true; do
    attempt=$((attempt + 1))
    info "Making sure $1 is in Docker's Ollama$(size_of "$1")..."
    compose A exec ollama ollama pull "$1" && return 0
    warn "Couldn't download $1 into Docker's Ollama. The internet connection may have dropped, or the Ollama container stopped (check Docker Desktop)."
    [ "$YES" = 1 ] && [ "$attempt" -ge 2 ] && fail "Couldn't download $1. Run ./start.sh again to retry."
    choose "[R]etry or [Q]uit?" "RQ" "R"
    [ "$CHOICE" = "Q" ] && quit "Stopped. The app is set up; run ./start.sh again to finish downloading the models."
    # The container may have been stopped or removed: bring it back before retrying.
    compose A up -d
  done
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

# Prints the page to open first: the dashboard while the library is empty, so
# people can look at the demo documents and load them there; the website after.
first_page() {
  local demo docs
  demo="$(http_get "http://127.0.0.1:$1/api/demo")"
  docs="$(printf '%s' "$demo" | json_field documents)"
  if [ -n "$docs" ] && [ "$docs" != "0" ]; then
    ok "Your library has $docs documents" >&2; echo "/site"
  else
    info "The library is empty. The dashboard lets you look through the demo company's documents, then load them with one click." >&2
    echo "/"
  fi
}

# --- Commands --------------------------------------------------------------------

stop_route() {
  if [ "$1" = "C" ]; then
    if [ -f "$DATA_DIR/app.pid" ] && kill "$(cat "$DATA_DIR/app.pid")" 2>/dev/null; then ok "App stopped (it was running with Python)"
    else info "The app wasn't running"; fi
    rm -f "$DATA_DIR/app.pid"
  else
    docker_state
    if [ "$DOCKER_STATE" = "running" ]; then
      compose "$1" down && ok "App stopped (it was running in Docker). Your documents and models are kept."
    else
      warn "Docker isn't answering, so the containers couldn't be stopped. Start Docker and run stop again."
    fi
  fi
}

do_stop() {
  read_settings
  [ -n "$START_ROUTE" ] || { say "Nothing to stop: start.sh hasn't been run here."; return 0; }
  stop_route "$START_ROUTE"
}

# Runs `python -m app.cli <args>` against this setup's data: the venv for route C, a
# one-off app container (with the data volume) for Docker. $1 = route, $2 = extra
# docker run options (or ""), the rest = app.cli arguments.
run_cli() {
  local route="$1" extra="$2"; shift 2
  if [ "$route" = "C" ]; then
    [ -x "$ROOT/backend/.venv/bin/python" ] || fail "The Python environment isn't set up: run ./start.sh first."
    (cd "$ROOT/backend" && DATA_DIR="$DATA_DIR" .venv/bin/python -m app.cli "$@")
  elif [ -n "$extra" ]; then
    compose "$route" run --rm --no-deps -v "$extra" app python -m app.cli "$@"
  else
    compose "$route" run --rm --no-deps app python -m app.cli "$@"
  fi
}

# Backs up now: through the running app (its job worker pauses indexing meanwhile),
# or with the app stopped through app.cli (decision 0015).
do_backup() {
  read_settings
  [ -n "$START_ROUTE" ] || fail "Not set up yet: run ./start.sh first."
  local port="${APP_PORT:-8000}" id jobs status
  if http_get "http://127.0.0.1:$port/health" | grep -q '"status"'; then
    id="$(curl -s -m 10 -X POST "http://127.0.0.1:$port/api/backups" | json_field job_id)"
    info "Backing up through the running app..."
    while true; do
      sleep 2
      jobs="$(http_get "http://127.0.0.1:$port/api/jobs")"
      status="$(printf '%s' "${jobs#*\"id\":$id,}" | json_field status)"
      case "$status" in
        completed) ok "Backup written (see the console's Backups page)"; return 0 ;;
        failed) fail "The backup failed; see the Queue page." ;;
      esac
    done
  fi
  info "The app isn't running, so the backup is made directly."
  run_cli "$START_ROUTE" "" backup
}

# Restores a backup: stops the app, restores (the current data is backed up first),
# and starts the app again.
do_restore() {
  [ -n "$TARGET" ] || fail "Which backup? Usage: ./start.sh restore <name or .zip file>. The console's Backups page lists them."
  read_settings
  [ -n "$START_ROUTE" ] || fail "Not set up yet: run ./start.sh first."
  local route="$START_ROUTE" arg="$TARGET" extra=""
  step "Restoring $TARGET"
  info "Stopping the app first: a restore needs it stopped."
  stop_route "$route"
  if [ -f "$TARGET" ]; then
    local full; full="$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")"
    if [ "$route" = "C" ]; then arg="$full"
    else extra="$full:/restore/backup.zip:ro"; arg="/restore/backup.zip"; fi
  fi
  run_cli "$route" "$extra" restore "$arg" || fail "The restore didn't finish; see the messages above. Run ./start.sh to start the app again."
  ok "Restored. Starting the app again..."
  do_start
}

do_status() {
  read_settings
  [ -n "$START_ROUTE" ] || { say "Not set up yet: run ./start.sh"; return 0; }
  local port="${APP_PORT:-8000}" body names
  say "Set up to run $(describe_route "$START_ROUTE")."
  say "Chat model $CHAT_MODEL, at http://localhost:$port"
  if [ "$START_ROUTE" != "C" ]; then
    docker_state
    if [ "$DOCKER_STATE" = "running" ]; then names="$(container_names "$START_ROUTE")"; [ -n "$names" ] && say "Containers: $names"; fi
  fi
  body="$(http_get "http://127.0.0.1:$port/health")"
  if [ -z "$body" ]; then say "The app isn't running. Start it with ./start.sh"; else say "Health: $body"; fi
}

choose_chat_model() {
  # Sets CHAT_MODEL. $1 = suggested, $2 = 1 when Ollama on this computer can be asked.
  local suggested="$1" chat="" m default=""
  if [ "$2" = 1 ]; then
    for m in $(ollama_models); do is_chat_model "$m" && chat="$chat $m"; done
  fi
  if [ -z "$chat" ]; then
    CHAT_MODEL="$suggested"
    if [ "$YES" = 0 ]; then
      prompt_line "  Chat model to use [$suggested$(size_of "$suggested")]:"
      [ -n "$ANSWER" ] && CHAT_MODEL="$ANSWER"
    fi
    return 0
  fi
  for m in $chat; do [ "${m%:latest}" = "$suggested" ] && default="$m"; done
  [ -z "$default" ] && default="$(echo "$chat" | awk '{print $1}')"
  say "  Ollama already has these chat models:$chat"
  CHAT_MODEL="$default"
  if [ "$YES" = 0 ]; then
    prompt_line "  Use $default? Press Enter, or type another name (it's downloaded if missing):"
    [ -n "$ANSWER" ] && CHAT_MODEL="$ANSWER"
  fi
}

explain_check() {
  # What --check reports: where the questions would lead with the default answers.
  step "3. How to run it"
  if [ -n "$START_ROUTE" ] && [ "$RECONFIGURE" = 0 ]; then
    info "Saved choice: run $(describe_route "$START_ROUTE"). (--reconfigure asks again.)"
  else
    [ "$DOCKER_STATE" = "down" ] && info "Docker isn't answering: it would ask to wait for it, use Python instead, or quit."
    [ "$1" = "stopped" ] && info "Ollama isn't running: it would start it."
    if [ "$DOCKER_STATE" != "missing" ] && [ "$1" != "missing" ]; then
      if [ "$OS" = "Linux" ]; then
        info "It would ask 'Run the app in Docker?'. On Linux Docker can't reach this computer's Ollama, so the default is route C (Python) when Python is installed; yes means route A."
      else
        info "It would ask 'Run the app in Docker?'. Yes (the default): route B; no: route C."
      fi
    elif [ "$DOCKER_STATE" != "missing" ]; then
      info "It would ask 'Run Ollama inside Docker?'. Yes (the default): route A; no: install Ollama, then route B."
    else
      info "Without Docker: route C (Python), installing Ollama and Python first if needed, after asking."
    fi
  fi
  info "Chat model: ${CHAT_MODEL:-$2}; embedding model: $EMBEDDING_MODEL"
  say ""; say "--check: nothing was changed."
}

do_start() {
  say ""
  say "Local RAG with Ollama: one-command start"
  say "Everything runs on this computer; your documents never leave it."
  read_settings
  local saved_route="$START_ROUTE" port="${APP_PORT:-8000}" ram_gb free_gb suggested
  local o_state docker_ok=0 host_ollama=0 ollama_in_docker=0 why_no_docker="Docker isn't installed" route m p names

  if [ -n "$saved_route" ] && [ "$CHECK" = 0 ] && [ "$RECONFIGURE" = 0 ] \
    && http_get "http://127.0.0.1:$port/health" | grep -q '"status"'; then
    ok "The app is already running $(describe_route "$saved_route"), at http://localhost:$port"
    open_url "http://localhost:$port/site"; return 0
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
  o_state="$(ollama_state)"
  case "$o_state" in
    running) ok "Ollama is running on this computer" ;;
    stopped) info "Ollama is installed on this computer but not running" ;;
    *) info "Ollama isn't installed on this computer" ;;
  esac
  docker_state
  case "$DOCKER_STATE" in
    running) ok "Docker is running (engine $DOCKER_DETAIL)" ;;
    down) info "Docker is installed but isn't answering" ;;
    *) info "Docker isn't installed (optional: https://www.docker.com/products/docker-desktop/)" ;;
  esac

  if [ "$CHECK" = 1 ]; then explain_check "$o_state" "$suggested"; return 0; fi

  step "3. How to run it"
  find_python
  if [ -n "$saved_route" ] && [ "$RECONFIGURE" = 0 ]; then
    # Reuse the saved route, making sure what it needs is up. No silent switching.
    route="$saved_route"
    info "Using your saved choice: run $(describe_route "$route"). (--reconfigure asks again.)"
    if [ "$route" != "C" ]; then
      [ "$DOCKER_STATE" = "missing" ] && fail "Docker isn't available, but this was set up to run in Docker. Run ./start.sh --reconfigure to choose again."
      [ "$DOCKER_STATE" = "down" ] && ensure_docker 0
    fi
    if [ "$route" != "A" ]; then
      [ "$o_state" = "missing" ] && fail "Ollama isn't available on this computer, but this setup uses it. Run ./start.sh --reconfigure to choose again."
      [ "$o_state" = "stopped" ] && ensure_host_ollama 0
    fi
  else
    [ "$DOCKER_STATE" = "running" ] && docker_ok=1
    if [ "$DOCKER_STATE" = "down" ]; then
      ensure_docker 1
      if [ "$DOCKER_RESULT" = "running" ]; then docker_ok=1; else why_no_docker="you chose Python instead of waiting for Docker"; fi
    fi
    [ "$o_state" = "running" ] && host_ollama=1
    if [ "$o_state" = "stopped" ]; then
      ensure_host_ollama "$docker_ok"
      if [ "$OLLAMA_RESULT" = "running" ]; then host_ollama=1; else ollama_in_docker=1; fi
    fi

    if [ "$docker_ok" = 1 ] && [ "$host_ollama" = 1 ] && [ "$OS" = "Linux" ]; then
      # Linux: Ollama listens on 127.0.0.1 only, so a container can't use it.
      if [ -n "$PYTHON" ]; then
        if ask "Run the app in Docker? On Linux Docker can't use this computer's Ollama, so it would run its own and download the models again (about 3 GB). No runs it with Python next to your Ollama." n; then route="A"
        else route="C"; why_no_docker="you chose Python, which reuses your Ollama and models"; fi
      else
        route="A"; info "Python 3.11+ isn't installed, so the app and Ollama run in Docker (the models download again, about 3 GB)."
      fi
    elif [ "$docker_ok" = 1 ] && [ "$host_ollama" = 1 ]; then
      if ask "Run the app in Docker? (recommended; it uses the Ollama and models already on this computer)"; then route="B"
      else route="C"; why_no_docker="you chose to run without Docker"; fi
    elif [ "$docker_ok" = 1 ]; then
      [ "$ram_gb" -lt 12 ] && warn "With $ram_gb GB of RAM, Docker gets only part of it, so answers from Ollama inside Docker are much slower (minutes). Ollama installed on this computer is faster."
      if [ "$ollama_in_docker" = 1 ] || ask "Ollama isn't installed on this computer. Run it inside Docker? (recommended: nothing to install; the models download into Docker, about 3 GB)"; then
        route="A"
      else
        install_ollama || fail "Ollama is needed. Install it from https://ollama.com/download, or run this again and choose Ollama inside Docker."
        if [ "$OS" = "Linux" ]; then route="C"; else route="B"; fi
      fi
    else
      route="C"
      if [ "$host_ollama" = 0 ]; then
        info "Running without Docker needs Ollama on this computer."
        install_ollama || fail "Ollama is needed. Install it from https://ollama.com/download, or install Docker, then run this again."
      fi
    fi
    if [ "$route" = "C" ]; then ok "Will run $(describe_route C): $why_no_docker."
    else ok "Will run $(describe_route "$route")."; fi
  fi

  if [ "$route" = "C" ]; then
    if [ -z "$PYTHON" ]; then
      info "Running with Python needs Python 3.11 or newer."
      install_python || fail "Python 3.11+ is needed (https://www.python.org/downloads/), or install Docker."
    fi
    ok "Python: $PYTHON"
  fi

  # Switching from another way: stop it first, so the port is free.
  if [ -n "$saved_route" ] && [ "$saved_route" != "$route" ]; then
    info "Switching from route $saved_route to route $route; stopping the old one first."
    stop_route "$saved_route"
    info "Each way keeps its own library (data/ for Python, a Docker volume for Docker), so the demo is loaded again here."
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
    compose "$route" pull --quiet app 2>/dev/null || warn "Couldn't check for a newer app image; using the one already downloaded."
    compose "$route" up -d || fail "docker compose up failed; see the messages above."
    if [ "$route" = "A" ]; then
      for m in "$EMBEDDING_MODEL" "$CHAT_MODEL"; do pull_in_docker "$m"; done
    fi
  fi
  wait_healthy "$port" || warn "The app isn't fully healthy yet. Open http://localhost:$port and click Troubleshoot."

  step "6. The demo company"
  local first
  first="$(first_page "$port")"

  step "Ready"
  say "  Running $(describe_route "$route")."
  if [ "$route" != "C" ]; then names="$(container_names "$route")"; [ -n "$names" ] && say "  Containers (see them in Docker Desktop): $names"; fi
  [ "$OLLAMA_STARTED_HERE" = 1 ] && say "  Ollama was started by this script; it keeps running after this window closes."
  say ""
  say "  Company website:  http://localhost:$port/site"
  say "  Employee portal:  http://localhost:$port/intranet"
  say "  Admin console:    http://localhost:$port"
  say ""
  say "  Stop: ./start.sh stop   Status: ./start.sh status   Choose another way: ./start.sh --reconfigure"
  say "  Your answers are saved in .env. This run's log: data/start.log"
  [ "$first" = "/" ] && say "  Opening the dashboard: click 'See the documents', then 'Load the demo company'."
  open_url "http://localhost:$port$first"
}

case "$COMMAND" in
  stop) do_stop ;;
  status) do_status ;;
  backup) do_backup ;;
  restore) do_restore ;;
  *)
    if [ "$CHECK" = 0 ]; then
      # A log of each start (overwritten every time) for troubleshooting.
      mkdir -p "$DATA_DIR" && exec > >(tee "$LOG_FILE") 2>&1 && LOGGING=1
    fi
    do_start
    ;;
esac
