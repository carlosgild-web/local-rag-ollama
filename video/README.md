# The README video

Records "a real model, under the hood" from the running app (decision 0043, tooling ported
from luna-hybrid-agent). [docs/video.md](../docs/video.md) says what it shows. Recording needs
Windows (Edge), ffmpeg on the `PATH`, Ollama with `qwen2.5:3b` and `bge-m3`, and the backend
venv.

```bash
cd video && npm ci          # @playwright/test only; uses the installed Edge
npm run video:check         # every [file, symbol] in storyboard-ollama.json still resolves
npm run video:test          # how compose.mjs cuts a take
npm run video:smoke         # ~15 s: the 1920x1080 stage -> out/smoke/ (any running app)
```

## Record it (two passes, decision 0043)

On the 7.2 GB development laptop the model and the recording browser don't fit together, so
the model runs first, alone, and the recording replays its answers:

1. Close every other app. Ollama with `OLLAMA_MAX_LOADED_MODELS=2` keeps both models loaded
   for pass 1 (decision 0042 has the timings).
2. **Pass 1:** `start.cmd video`, then
   `backend/.venv/Scripts/python video/capture.py --out video/out/pass1`: the storyboard's
   `script` through the app's API, no browser (the intake, the questions on `qwen2.5:3b`, the
   new version). Then `start.cmd video stop`.
3. **Pass 2:** `powershell -File video\replay.ps1` (fresh data again, `qwen2.5:3b` unloaded,
   the app on port 8010 replaying pass 1), then
   `VIDEO_REPLAY_DIR=video/out/pass1 npm run video:ollama`. It writes to `out/ollama/`:
   - `take.webm`, the stage as recorded;
   - `video.mp4`, with every wait over 3 s shortened to 1 s and labelled with its real
     length (a model wait shows pass 1's);
   - `video-readme.mp4` (1280x720, under 10 MB), `poster.png` and `subtitles.en.srt`;
   - `take.json` (the model, the rows that never matched, `replay_of`), `events.json`,
     `shown.json`, `inspect-<turn>.json`, `session-<turn>.json`.
4. `powershell -File video\replay.ps1 -Stop`.

`npm run video:verify` re-checks a take: the rows, every payload against the capture, each
inspector ranking against the passages the chat sent, every answer and its passages against
pass 1, the model, no paths.

### The dry run

The same steps on the storyboard's scripted answers (`dry_answer`), with retrieval, indexing
and everything else live:

```bash
powershell -File video\replay.ps1 -Dry
cd video && npm run video:dry          # -> out/dry/
```

## Files

| File | Role |
|---|---|
| `storyboard-ollama.json` | The turns, the `script` both passes follow, and the rows: trigger, subtitle, callouts, payload source |
| `record.spec.ts` | The take: guard, capture, conductor, scenes (`@smoke`, `@dry`, `@ollama`) |
| `stage.html`, `stage.js` | App iframe, "Under the hood" panel, subtitles, slides |
| `payload.mjs` | How a row's payload is cut from the capture; shared by the take and the checks |
| `lines.mjs` | `file:symbol` → current line and excerpt |
| `capture.py`, `replay_server.py`, `replay.ps1` | Pass 1 (the script on Ollama, no browser) and pass 2 (the app replaying pass 1's answers) |
| `cues.mjs`, `compose.mjs` | Cues, checks, wait cuts, `.mp4`, `.srt`, the README copy (ffmpeg) |
| `compose.test.mjs` | `npm run video:test` |
| `fixtures/v2/` | Version 2 of the returns policy (45 days instead of 30) |

Where the panel's data comes from: the chat's SSE events (the passages, the answer as it
streamed), the stored answer after citation repair (`GET /api/sessions/{id}`), the
retrieval inspector on the turn's own question and shelf (`POST /api/retrieve/inspect`, read
only, the chat's own code: vector and keyword ranks, the fused score, the cut, the exact
prompt), and the app's own JSON answers as the browser received them (the intake's
suggestions, the inspector page, the evaluation comparison, the rollback).

## Findings (phase 10, steps R4-R5, 2026-11-27)

Three dry takes on scripted answers before the first Ollama take.

| # | Finding | Kind | Fix |
|---|---|---|---|
| F1 | The hook slide covered the app, so the click on the console's notice was intercepted | Tooling | The slide is hidden before scene 1 loads the Library |
| F2 | The stored answer was read from the wrong path | Tooling | `GET /api/sessions/{id}` |
| F3 | A document's details open on Content; "Restore this version" is under Versions | Tooling | The take opens the Versions tab first |
| F4 | "30 days, from version 1" stayed on screen through the whole upload of version 2 | Storyboard | Row 5.3a as the new file is picked |
| F5 | The first dry take ran 3:17. Holds were 102 s; most of the rest was each page load waiting 6 s for a notice that, once closed, stays closed | Tooling | Only the first page waits for it; hold factor 0.5; row 4.2 dropped; faster typing. Third dry take: 2:35 |
| F6 | The take started both evaluation runs at once; the app refuses a run while another is in progress, and the take kept polling a run that didn't exist | Tooling | One run at a time, every response checked |

Checked in the third dry take: all 24 rows shown, 13 payloads equal the capture, the four
inspector rankings equal the passages the chat sent, no local path in any payload or in the
app's text.
