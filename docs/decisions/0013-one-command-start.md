# 0013: One-command start for testers

**Status:** accepted (2026-11-10)

## Context

A fresh-clone test, done as an outside tester would with only the GitHub URL, showed how much the manual setup asked of people:
- pick one of three ways, and type four or five commands
- know whether Ollama was already installed

Way A failed outright next to an installed Ollama (fixed in 0005's port note). It also spent 30 minutes downloading an Ollama image and the models again, which way B would have reused. The people most likely to try a local RAG project are the ones who already have Ollama.

## Decision

- **`start.cmd` (Windows) and `start.sh` (macOS, Linux) at the repo root**, with the same steps and prompts.
  - The Windows logic is in `scripts/start.ps1`. It's written for Windows PowerShell 5.1, which every Windows machine has.
  - `start.cmd` runs it with `-ExecutionPolicy Bypass` for that one run, because Windows blocks `.ps1` files by default.
  - `start.sh` is written for bash 3.2, which macOS ships.
- **The script picks the route from what's installed** and says why:
  - **B:** Docker plus the computer's own Ollama, reusing its models.
  - **A:** Docker only.
  - **C:** Python plus Ollama, no Docker.

  On Linux, the computer's Ollama listens on 127.0.0.1 only and a container can't reach it, so C is preferred there when Python is present.
- **Model choice:** it suggests `qwen2.5:3b` under 12 GB of RAM ([0004](0004-small-chat-model-on-low-ram.md)), lists the chat models Ollama already has, and downloads only what's missing.
- **Installs only with consent, from official sources:**
  - Ollama: winget, Homebrew, or ollama.com's Linux installer (default No)
  - Python: winget or Homebrew
  - Docker Desktop is never installed (admin rights and a restart); the script only offers to start it.
- **Route C needs no Node.** `release-web.yml` attaches the built web app (`web-dist.zip`) and its SHA-256 to every Release. The script downloads it and checks the hash; if that fails and Node is present, it builds the web app instead.
- **The answers are saved in the git-ignored root `.env`** (`START_ROUTE`, `CHAT_MODEL`, `EMBEDDING_MODEL`, `APP_PORT`). Docker Compose reads the same file, so a by-hand `docker compose up` matches the script. `compose.yaml` takes `APP_PORT`, and the script picks 8001–8010 when 8000 is taken.
- **The app guides first-time setup too.** With an empty library, the dashboard offers *Load the demo company*: a `seed_demo` job through the same service as `app.cli seed-demo`, audited. A missing model already has a Download button in the troubleshooter.

## Consequences

- **What a tester types:** `git clone …`, `cd …`, `.\start.cmd`. The manual ways stay in the guide under "Or by hand".
- **Two scripts to keep in step.** CI lints both (`shellcheck`, PSScriptAnalyzer) and runs `--check` on Ubuntu, macOS and Windows. Full routes are checked by hand.
- **Route C uses the latest Release's web app.** A clone of `main` between releases gets the web app from the last tag. For changes to the UI, build it with Node.

## Addendum (2026-11-10): ask, never fall back silently

A tester with Docker Desktop installed and running ended up on route C (Python) without noticing, and nothing showed in Docker Desktop. The first version picked the route by itself. When Docker didn't answer, or didn't start within 2 minutes, it quietly used route C and said "no Docker". It also kept no log, so the cause couldn't be recovered. Changes:

- **The route is asked, with a recommended default.**
  - Docker and Ollama present: *Run the app in Docker?* (yes → B, no → C).
  - Docker without Ollama: *Run Ollama inside Docker?* (yes → A, no → install Ollama, then B).
  - On Linux, Docker can't reach the computer's Ollama, so the question says the models would download again, and the default is C when Python is installed.
- **Installed but not running:**
  - It starts Ollama the usual way for each OS: the tray app on Windows, the app on macOS, the systemd service on Linux (with sudo, asked).
  - It starts Docker Desktop.
  - If either still doesn't answer, it shows the reason and offers *wait/retry*, the other way, or *quit*. It switches only on an explicit choice, and `--yes` stops instead of switching.
- **Visibility:**
  - The final summary and `status` say how the app runs ("in Docker (route B)", plus the container names) and whether the script started Ollama.
  - Each start is logged to `data/start.log`.
- **`--reconfigure` switching** stops the previous way first, and says that each way keeps its own library.
- **Ollama inside Docker needs memory.** Route A was tested on the 7.2 GB laptop. The models downloaded and retrieval worked, but loading `qwen2.5:3b` inside Docker's 3.4 GB VM took more than two minutes, and the answer timed out. The same question answered in about a minute on route B. Under 12 GB of RAM, the route A question now warns, and the guide says route A needs about 16 GB.
- **Testing the questions:** the answers are fed through stdin, as well as `--yes`. Test-only flags (`--no-host-ollama`, `--no-docker`, `--ollama-start-fails`) simulate the missing and failing cases.
- **The demo is loaded from the dashboard, not the script (2026-11-12).** The script used to ask "Load the demo company now?" in the terminal. Now it opens the dashboard while the library is empty. The demo card there lists the 11 original documents (open or download) before anything is indexed, so people see what will be processed.
