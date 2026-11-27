# The video: a real model, under the hood

A 2½-minute take of the app on the evaluated setup: `qwen2.5:3b` for answers and `bge-m3` for embeddings, both on Ollama, on the 7.2 GB development laptop's CPU. The app is on the left, unchanged. The panel on the right shows the code and the data behind each step, taken from the take itself. No sound.

The video is in the [README](../README.md#the-2½-minute-video-a-real-model-under-the-hood); a lighter copy plays on the [project page](https://carlosgild-web.github.io/local-rag-ollama/).

## What it shows

| Time | Step | What to notice |
|---|---|---|
| 0:00 | Title | Four parts: adding files, hybrid search, grounded answers, versions |
| 0:06 | Adding three files | Each file gets a shelf and tags from `bge-m3` similarity to the documents already there; one is marked "please check". Nothing is indexed until **Process** |
| 0:20 | Indexed | Stored once by SHA-256, cut into pieces, indexed in Chroma (vectors) and SQLite FTS5 (keywords). The analysis and indexing waits are cut, with their real length |
| 0:25 | A question on the hr shelf | The panel: each passage's vector rank, keyword rank and fused score, then the first lines of the exact prompt the model gets |
| 0:38 | The answer | `qwen2.5:3b` streams it. The panel shows what the model wrote and what was stored: it cited `[1] [2]`, and citation repair kept only `[2]`, the passage with the dates |
| 0:59 | The passage | The citation opens the holiday announcement, page 1. The marked line holds the dates |
| 1:02 | A question the documents don't answer | Dental coverage: the closest passages come back, none holds it, and the reply is "not found in the documents" |
| 1:14 | Versions | The return window is **30 days** (v1). The policy file comes back with the same name and new content: the app makes it v2. Asked again: **45 days**. Then **Restore this version**: v1 is active again, and the panel shows its unchanged hash and passage count, so nothing was embedded again |
| 2:02 | The retrieval inspector | Every passage with its ranks and where the cut to the model falls. Moving the vector weight re-ranks at once; the question's embedding is reused |
| 2:13 | Evaluation | Two runs of the 53-question golden set: vectors only (right file in the top 5 for 96%, MRR 0.865) against hybrid (100%, MRR 0.930) |
| 2:19 | End card | Repository, author |

## Is it real?

- **The models are real, and their run is replayed.** On this laptop the model and a recording browser don't fit in memory together, so the take was made in two passes ([decision 0043](decisions/0043-readme-video-two-passes.md)). First `qwen2.5:3b` answered the four questions with no browser running. Then the app was started again from fresh data and recorded while, for each question, it streamed the model's recorded answer at the recorded pace. The banner on every frame says so.
- **Only the model's text is replayed.** Everything else ran live during the recording: `bge-m3`, the two indexes, the glossary, retrieval, the prompt, citation repair, adding files, versions, the rollback, the inspector and the evaluation runs.
- **The replay can't drift.** Each recorded answer is found by the SHA-256 of its exact prompt, so it only plays if the passages are the same. After the take, a check confirms that each question got the same five passages and the same answer as in the model's run, that every payload in the panel equals what the take captured, and that each inspector ranking is the order the chat sent its passages.
- **Waits are cut and labelled.** Any stretch over 3 s with nothing new on screen is shortened to 1 s, with a label giving its real length. For a model answer that stretch is what remains after the panel's rows: the full answers took 27, 24, 19 and 18 s.
- **The two evaluation runs** were started through the API just before the take (retrieval only, about a minute each), and the scene opens their comparison.
- **The files are fictional.** The three new files and version 2 of the returns policy are written for the demo: [`e2e/showcase/intake/`](../e2e/showcase/intake/) and [`video/fixtures/v2/`](../video/fixtures/v2/).

## Record it again

[`video/README.md`](../video/README.md) has the steps (`start.cmd video`, `capture.py`, `replay.ps1`, `npm run video:ollama`), the dry run, and the findings from the dry takes.
