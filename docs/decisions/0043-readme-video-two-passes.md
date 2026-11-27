# 0043: The README video, recorded in two passes on the real models

**Status:** accepted (2026-11-27)

## Context

PLAN.md Phase 10 re-records the demo video to the portfolio's standard: the real app on the real local models (`qwen2.5:3b` and `bge-m3` on Ollama, the evaluated setup), an "Under the hood" panel that shows what the code does at each step, and long waits cut to 1 s with their real length in a label. The v1.0.1 video was recorded by hand (OBS) and had no panel.

On the 7.2 GB development laptop, `qwen2.5:3b`, `bge-m3`, a 1920x1080 browser and a recorder don't fit together. Luna Hybrid Agent hit the same wall with a larger model (its decision 0043): the browser stopped painting under memory pressure, and model calls slowed past their timeouts.

## Decision: two passes

- **Pass 1, the model alone** (`video/capture.py`). With `start.cmd video` running (decision 0042), it follows the storyboard's `script` through the app's own API with no browser: the intake of three files, the questions, version 2 of the returns policy, the question again. For each question it saves the exact prompt's SHA-256 (from the retrieval inspector, the chat's own code), the passages, and every streamed piece of the answer with its time.
- **Pass 2, the recording** (`video/replay.ps1`, `video/replay_server.py`, `npm run video:ollama`). Fresh demo data again, `qwen2.5:3b` unloaded, and the real app with one change: the chat model's call streams pass 1's answer for the same prompt, at pass 1's pace. Everything else runs live: `bge-m3`, Chroma, SQLite FTS5, the glossary, the prompt, citation repair, the intake, indexing, versions, the inspector and the evaluation. A prompt pass 1 never saw stops the answer with an error instead of showing something made up.
- **Checked after every take** (`video/cues.mjs`): each answer and the passages it was given equal pass 1's (so the prompt was the same), every payload on screen equals its capture, each inspector ranking is the order the chat sent its passages, and no local path is visible.
- **Labelled.** The banner says the answers are replayed from the model's run. A model wait is cut to 1 s and labelled with pass 1's real length; so are the analysis and indexing waits of pass 2.

## Decision: the panel's data

- The chat's SSE events (the passages, the answer as it streamed), the stored answer after citation repair, and the app's own JSON answers as the browser received them (the intake's suggestions, the rollback, the inspector page, the evaluation comparison).
- The vector and keyword ranks, the fused score, the cut to the model and the exact prompt come from `POST /api/retrieve/inspect` on the turn's own question and shelf. The plan named a separate `introspect.py` for this; the inspector already runs the chat's own retrieval code read only, so the video uses it, and `cues.mjs` checks that its ranking is the one the chat sent.
- Code excerpts are found by `file:symbol` at take time (`lines.mjs`); `npm run video:check` fails when a symbol is gone.
- The evaluation scene compares two retrieval-only runs of the 53-question golden set (vectors only and hybrid), made through the API just before the take. Answer runs take about half a minute per question on the laptop, so the video doesn't run them; the README's answer table stays the reference.

## Consequences

- `video/` holds the tooling (Playwright is a dev dependency of `video/` only; Edge, nothing downloaded). Its outputs go to `video/out/` (gitignored).
- The video can be recorded again from any commit: `video/README.md`.
- No product code changed for the video.
- The published take (2026-11-27): 2:25, eight waits cut and labelled, every check passed. Three dry takes and three recordings of pass 2 from one pass 1; findings F1-F9 in `video/README.md`.
- The README plays `video-readme.mp4` (1280x720, 8.2 MB) from GitHub's `user-attachments`; GitHub Pages plays a lighter copy at the same address as before (`docs/showcase/demo.mp4`, 2.4 MB), so the project page keeps working.
