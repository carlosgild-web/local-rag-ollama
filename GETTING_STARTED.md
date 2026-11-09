# Getting started

Set up the app, load the demo company, and try everything it does, step by step. It takes about 15 minutes, plus the model download.

> Prefer a web page? The same guide is at **[carlosgild-web.github.io/local-rag-ollama/getting-started.html](https://carlosgild-web.github.io/local-rag-ollama/getting-started.html)**.

## 1. What you need

| | |
|---|---|
| **Memory** | 8 GB of RAM at least; 16 GB is comfortable. On 8 GB, use the small chat model (`qwen2.5:3b`). |
| **Disk** | About 4 GB for the small models (`qwen2.5:3b` and `bge-m3`), or 7 GB with `llama3.1`. |
| **Software** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) (way A or B), or Python 3.11+ and Node 22 (way C). For ways B and C, also [Ollama](https://ollama.com). |

No GPU or internet connection is needed after the models are downloaded, and nothing you upload ever leaves your computer.

```bash
git clone https://github.com/carlosgild-web/local-rag-ollama.git
cd local-rag-ollama
```

## 2. Start the app (pick one way)

### A. Docker, everything in containers (easiest)

```bash
docker compose up -d
docker compose exec ollama ollama pull bge-m3
docker compose exec ollama ollama pull llama3.1
```

On a machine with 8 GB of RAM, use the small chat model instead:

```bash
CHAT_MODEL=qwen2.5:3b docker compose up -d
docker compose exec ollama ollama pull bge-m3
docker compose exec ollama ollama pull qwen2.5:3b
```

In Windows PowerShell, set the variable first: `$env:CHAT_MODEL="qwen2.5:3b"; docker compose up -d`.

The app image is pulled ready-made from GitHub's registry. To build it from the source instead, add `--build` to the first command.

### B. Docker, with the Ollama already on your computer

```bash
ollama pull bge-m3
ollama pull llama3.1          # or qwen2.5:3b, then start with CHAT_MODEL=qwen2.5:3b
docker compose -f compose.yaml -f compose.host-ollama.yaml up -d
```

### C. Without Docker

```bash
ollama pull bge-m3
ollama pull llama3.1          # or qwen2.5:3b, with CHAT_MODEL=qwen2.5:3b set below

cd frontend && npm ci && npm run build            # build the web app first
cd ../backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # macOS/Linux: .venv/bin/pip
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Settings are environment variables, such as `CHAT_MODEL`, `OLLAMA_BASE_URL` and `DATA_DIR`. See [`backend/.env.example`](backend/.env.example).

## 3. Check that it's running

Open **http://localhost:8000**. The console's dashboard shows **All systems OK** once Ollama, the database, the search index and the background worker all answer.

![The console dashboard](docs/showcase/img/28-console-dashboard.jpg)

If something is red, click **Troubleshoot**. It names the cause and the fix, for example "Ollama isn't running" or "the chat model isn't installed".

## 4. Load the demo company

Hilda & Luna Beadworks is a fictional bead maker with 11 documents: a handbook, safety training, a catalog, a price sheet, an FAQ and more.

```bash
docker compose exec app python -m app.cli seed-demo                 # ways A and B
cd backend && .venv/Scripts/python -m app.cli seed-demo             # way C
```

It creates four shelves (customer-support, hr, meetings, operations) and ends with `11 ingested, 0 skipped`. Running it again skips every file as a duplicate.

## 5. Take the tour

**① The company's website:** http://localhost:8000/site. The dark strip on top is the demo guide. It isn't part of the company's design; it shows reviewers the way.

![The public website](docs/showcase/img/22-site-home.jpg)

**② Employee login → Enter as demo employee.** The sign-in is a simulation: no accounts, one button.

![Simulated staff sign-in](docs/showcase/img/24-staff-signin.jpg)

**③ The intranet.** Click **How this demo works** in the banner for the path and things to try.

![The intranet with the demo guide](docs/showcase/img/25-intranet-demo-guide.jpg)

**④ Ask Luna** something, like "When does the company close for the holidays?", and open a source to see the exact passage. Switch to **ES** and ask in Spanish. Ask something the documents don't say, and Luna says so instead of guessing.

![Luna's answer with its source](docs/showcase/img/27-luna-source.jpg)

**⑤ Open the RAG admin console** from the banner. Under **Collections**, turn a shelf's **Visible in the employee portal** switch off, and Luna stops using it.

![Shelves with the portal switch](docs/showcase/img/29-collections-portal-switch.jpg)

**⑥ Try your own documents.** In **Library**, drop a few files or a whole folder. The app suggests a shelf and tags for each one; you confirm, and they're indexed. Then ask about them in **Chat**.

![Suggested shelves and tags](docs/showcase/img/04-suggestions.jpg)

The [reviewer walkthrough](docs/walkthrough.md) goes through the same tour in more detail.

## 6. Run the tests

```bash
cd backend
.venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -q                        # 179 tests, with fakes: no Ollama needed
.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .
cd ../frontend && npm run build                          # type check and build
```

The **end-to-end test** drives the running app with the real model, about 60 questions and every app mechanic. It takes 1–3 hours on a laptop CPU; see [`e2e/README.md`](e2e/README.md). CI runs the unit tests, the linters, the frontend build and a Docker build on every push.

## 7. If something goes wrong

| Problem | What to do |
|---|---|
| "Ollama isn't running" | Start Ollama (way B or C), or check `docker compose ps` (way A). The troubleshooter shows the address it's trying. |
| "Model not installed" | Run the `ollama pull` lines from step 2 for the models the app expects (`CHAT_MODEL`, `EMBEDDING_MODEL`). |
| Answers are slow | That's normal on a CPU: 20–60 seconds an answer. Use `qwen2.5:3b` on smaller machines. |
| Port 8000 is in use | Stop the other program, or change the left port in `compose.yaml` (`127.0.0.1:8001:8000`). |
| Start over with no documents | Way A or B: `docker compose down -v` (**deletes** the app's data and the downloaded models). Way C: delete `backend/data/`. |

To stop the app, run `docker compose down`; your documents and models are kept.

> **Security:** there are no logins. Run the app on your own computer or a private network only. See [SECURITY.md](SECURITY.md).
