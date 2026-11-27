# 0042: A video mode for the start scripts, and a harness for the README GIFs

**Status:** accepted (2026-11-27)

> **Numbering.** Decisions 0032–0041 belong to [Luna Hybrid Agent](https://github.com/carlosgild-web/luna-hybrid-agent), which carries this history forward. New records here start at 0042, so a number never means two things.

## Context

PLAN.md Phase 10 brings this repo to the portfolio's showcase standard: a README GIF of the main flow and a re-recorded video with an "Under the hood" panel, on the real local models. Both need the app to start from the same state every time, without touching the user's `data\` folder. Until now the only way to that state was a fresh install and a click on **Load the demo company**.

## Decision: `start.cmd video` (and `./start.sh video`)

- **Its own folder and port.** `DATA_DIR` is `data-video\` (gitignored) and the app listens on port 8010, so a normal start on 8000 and its library are left alone.
- **Wiped at every start.** The last video server is stopped (its `app.pid`), the folder is emptied (except this run's `start.log`), then the app starts.
- **The app's own calls.** The demo company is loaded with `POST /api/demo/seed`, the job behind the dashboard's button (11 documents embedded with `bge-m3`, and the glossary). The demo golden set is loaded with `POST /api/eval/demo`, the Evaluation page's button (53 questions).
- **The evaluated models.** `qwen2.5:3b` for answers and `bge-m3` for embeddings, the setup every number in the README's evaluation was measured with. Both are warmed (`keep_alive` 30 minutes) so the first question doesn't pay for loading them.
- **One route, no questions.** Python and the Ollama on this computer only (no Docker), no prompts. It fails with the fix when Ollama or a model is missing.
- `start.cmd video stop` stops it. `video` works with `start` and `stop` only.

Checked on the 7.2 GB development laptop: 84 s from an empty folder to "Ready for a take". Two starts in a row gave the same shelves, documents (by file hash), chunk texts, glossary and golden set.

**Both models on every question.** Each answer embeds the question with `bge-m3` and then runs `qwen2.5:3b`. With `OLLAMA_MAX_LOADED_MODELS=1` (the laptop's setting) Ollama swaps them each time: about 31 s to the first word and 35 s per answer. The video cuts these waits to 1 s and labels the real length (decision 0043).

## Decision: the README GIFs replay a recorded run on the real embeddings

`e2e/showcase/` (`npm run showcase`, Playwright on Edge, so nothing is downloaded) drives the built web app against `harness.py`:

- **Real:** the app as shipped, Ollama's `bge-m3`, Chroma, SQLite FTS5, the glossary, hybrid retrieval, the prompt, citation repair, and the intake's tags and shelf suggestions.
- **Replayed:** the chat model's text. `E2E_RECORD=1 npm run showcase` runs the same steps on `qwen2.5:3b` and saves each answer to `e2e/showcase/replay.json`, keyed by the question in the prompt (or `shelf-naming` for the intake's one naming call). A normal run streams those answers back word by word, so the GIF is the same on every run and takes seconds per answer instead of half a minute.
- **Why not fake embeddings,** as Luna's harness uses: the intake picks tags by comparing each file's embedding with the department vocabulary, so hash-based fake vectors would suggest meaningless tags, and the vector half of the hybrid ranking would be noise.
- The cost: making the GIFs needs Ollama with `bge-m3` (about 2 minutes to load the demo). They are not made in CI.
- The intake GIF adds three short fictional files from `e2e/showcase/intake/` to the loaded demo company. Each goes to an existing shelf (meeting notes to `meetings`, a supplier price update and a kiln log to `operations`, the kiln log marked "please check, it also fits `hr`"). The suggestions come from `bge-m3` alone; the one chat call the intake makes is the naming call for zero new shelves (see below), whose replayed answer, `{}`, changes nothing. The analysis (about 25 s of `bge-m3` on the laptop CPU) is cut from the GIF, and its caption says so.
- In the GIF and the passage screenshot, the passage line with the cited date is marked (a highlight; the text is unchanged). The console's low-memory notice, which the 7.2 GB laptop always shows, is closed with its own × before recording.

**Found on the way.** A first set of intake files went to a suggested new shelf. Asked to name it, `qwen2.5:3b` answered three times in a row with broken JSON that copied the prompt's example name (`employees-hr`), so the app used its keyword name instead, `documents`, as designed. The 3B model is weak at this task; it is noted in PLAN.md Phase 10 for a later look and is not changed in this phase (no product changes).

Also found: when every file goes to an existing shelf, `analyze_batch` still asks the chat model to name zero shelves (`_name_groups` with an empty list). The answer is unused, but on a small machine the call loads the chat model for nothing.

## Consequences

- The video tooling can assume `http://127.0.0.1:8010` and a known state; the GIF harness uses port 8020.
- Product code is unchanged: only the start scripts, `.gitignore`, and the new `e2e/showcase/` folder.
- `./start.sh video` follows the same steps. It was checked for syntax here (Windows) and by `shellcheck` in CI, and is not run on macOS or Linux, like the rest of the Python route there.
