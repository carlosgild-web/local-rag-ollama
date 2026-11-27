# What it does

Everything the app does, in more detail than the README's summary.

- **Answers only from your documents.** The model is told to use only the passages it was given. If they don't hold the answer, it replies *"not found in the documents"* instead of guessing.
- **Shows its sources.** Answers cite `[1]`, `[2]`… Click one to read the passage, with file, page and score. A warning appears if an answer cites nothing or cites a source that doesn't exist.
- **Organises new files for you.** Drop a folder and the app suggests a shelf for each file, either an existing one or a new one it names, plus tags such as `hr`, `price-list` or `q4-2026`. You change anything, then confirm. Nothing is indexed before you confirm.
- **Keeps versions.** The same file twice is skipped. A changed file becomes v2 and the old version stays available. A file that is almost the same as one already there, under another name, is flagged so it can become a new version instead of a second copy. Deletes go to a 30-day trash you can restore from.
- **Shows what it reads and what changed.** Click a document to read the text the app searches, see its versions, compare any two (changes highlighted), restore an earlier one, or fix a number in the text, saved as a new version with who changed what. The Library shows when each document was last updated.
- **Backs itself up.** One zip holds the database, the search index and your original files: made daily, or with *Back up now*. Restoring is one command, and the current data is saved first.
- **Explains problems in plain words.** A troubleshooter checks Ollama, the database, the search index and the background worker, and gives the cause and the fix. It can draft a (simulated) support ticket for the next support level.
- **Lets you look inside.** The retrieval inspector shows every passage a question finds, with its vector and keyword ranks and scores, where the cut to the model falls, and the exact prompt. Sliders for top-k, candidates, vector weight, a similarity floor and the reranker re-rank live. Settings live in versioned profiles you can compare and restore, and a models manager pulls, switches and deletes Ollama models (never one in use).
- **Watches folders.** Point it at a folder and new or changed files are added to a shelf by themselves, with the same versioning as an upload. Deleting a file there never deletes the document.
- **Works in English and Spanish**, with search that combines meaning (vectors) and exact words (keywords).
- **Comes with a demo company.** *Hilda & Luna Beadworks*, a fictional bead maker, has a public website at `/site` and an intranet at `/intranet`. Employees ask **Luna**, an assistant that searches every shelf the admin shares with the portal, in a floating chat or full screen, in Spanish or English. See [the employee portal](portal.md).

## Adding a document

1. The file is stored once under its SHA-256 hash.
2. It is parsed: PyMuPDF for PDF, python-docx for Word including tables, Tesseract OCR for scanned pages.
3. It is cut into overlapping pieces of about 600 tokens.
4. The pieces are embedded with `bge-m3` and indexed twice: in Chroma (vectors) and in SQLite FTS5 (keywords).

## Answering a question

1. The glossary writes the documents' words into the question: "vacation" is asked as "vacation (PTO, paid time off)".
2. Both indexes are searched on the chosen shelf.
3. The two rankings are fused with reciprocal rank fusion. An optional cross-encoder reranker can rescore the top 20.
4. The top 5 passages go into a prompt that allows answers only from them, with citations.
5. The answer streams back over server-sent events. When it ends, each `[n]` is checked against the passages and moved to the one that has the claim's figures, if the model cited the wrong one.
6. Every answer stores the passages and scores it used, so it can be reproduced later.

## Running it

- **One worker, no Redis.** An in-process job queue on SQLite runs indexing, rebuilds, backups and evaluation runs one at a time ([decision 0004](decisions/0004-small-chat-model-on-low-ram.md) has the low-RAM model choice).
- **Observable.** `/health` checks Ollama, SQLite, the vector store and the job worker. Every log line is JSON with a request id, and `/metrics` gives Prometheus the request, retrieval, answer and job timings, written with the standard library ([decision 0030](decisions/0030-prometheus-metrics.md)).
- **An optional password.** No sign-in by default and localhost only; `python -m app.cli set-password` (or `APP_PASSWORD`) puts one password on the console, the portal and the API ([decision 0026](decisions/0026-optional-password.md)).
- **Measured choices**, each written down: the one-line citation hint beat a long reminder, 6/6 vs 2/6 valid citations ([0007](decisions/0007-citation-reminder-and-check.md)); grouping by department beat clustering by similarity for suggesting shelves, 11/11 vs 5–19 of 30 ([0009](decisions/0009-suggested-shelves-and-tags.md)); the reranker is off by default, about 12 s a question on a laptop CPU for +0.02 MRR ([0023](decisions/0023-reranker.md)).
