# 0009: The app suggests a shelf and tags for every upload

**Status:** accepted (2026-11-07)

## Context

In the step 4 upload flow the user picked a shelf (collection) and typed tags *before* uploading. The user asked for the reverse: drop files or a folder, let the app analyse each document and suggest an existing shelf or a new one with a suggested name, plus tags, then review, change anything and approve. This is not in `PLAN.md`; it belongs to the UI-improvements branch (see 0008).

Constraints: everything runs locally, on a 7.2 GB laptop with `qwen2.5:3b` (0004), so analysis must not need one chat-model call per file.

## Decision

**Flow.** `POST /api/intake` stages the files under `DATA_DIR/uploads/intake/<batch>/` and queues a new job type, `analyze_intake`. The job writes its suggestions into the batch's `manifest.json`. Nothing is indexed and no shelf is created. `GET /api/intake/{id}` returns the suggestions. `POST /api/intake/{id}/confirm` creates the approved new shelves through `service.create_collection` and queues the normal `ingest` jobs from the staged files; it is audited as `intake_confirm`. `DELETE /api/intake/{id}` cancels, and batches older than 24 h are removed at startup.

**Hybrid analysis.** Per file: parse, SHA-256, and the step-4 `check_uploads` status (duplicates are left out, with the reason). Then embed the first 2,000 characters with `bge-m3`:

1. **Same name on an existing shelf** → that shelf; it becomes a new version.
2. **Existing shelf by similarity.** Each shelf's fingerprint is the first-passage vector (`chunk_index = 0`) of each active document, read through a new `VectorStore.get_vectors()`. A file's score for a shelf is the mean of its two best fingerprint similarities, plus 0.05 when its department tag is the shelf's majority department. A score of 0.60 or more suggests the shelf. A lead under 0.03 over the next shelf is marked "please check", with the alternative shown.
   - Measured, leave-one-out on the 11-file sample folder: chunk-level matching got 9/11, and the handbook and the holiday announcement were ambiguous.
   - The plan said "average of the shelf's vectors" (`mean_vector`). The first passages compare like with like, the excerpt against the opening of each document, so they were used instead.
3. **No shelf fits** → files are grouped by **audience** into suggested new shelves ("few broad shelves", the user's choice). Each department maps to an audience:
   - **staff:** hr, operations, quality
   - **business:** sales, customer-support, procurement, management

   A file's audience comes from its department tag, or from the closest department when the tag was too close to call. A subfolder's files stay together, on the subfolder's majority audience.
   - **Why not clustering by similarity.** Average-linkage clustering of the excerpt vectors was tried first. The two groups overlap: the lowest within-group similarity was 0.57 and the highest cross-group one 0.74. On random subsets of the sample, a median-based cut split the groups correctly in only 5–19 of 30 trials, and split an all-staff batch every time.
   - The department → audience rule placed 11/11 correctly.
4. **Shelf names.**
   - **One** chat-model call names every new shelf, given the file names and opening lines. It returns JSON `{"shelves": [{name, description}, ...]}`, in order. Each name is checked against the shelf-name rules and made unique.
   - **Names are matched to groups by content, not by position.** On 2026-11-08 the 3B model answered in the wrong order, and the business group got the name `employees-hr`. Each proposed name and description is now embedded and goes to the group whose average excerpt vector it is closest to, and only if that group is its best match.
   - A shelf the answer doesn't cover gets a keyword name from its department tags, e.g. `hr-quality` or `sales-customer-support`. The same happens if the model is unavailable or takes longer than 60 s; the slow call is abandoned, not awaited.
   - Measured on this 7.2 GB laptop with 0.1–0.3 GB of RAM free: excerpt embeddings took about 40 s for 11 files. The naming call needed 205 s with no limit and returned valid JSON, but names no better than the keyword ones ("product-catalog" for the whole business group). So the analysis takes about 1 minute on this machine plus up to 60 s for naming, and the keyword names are what you get here.
5. **Tags, at most 5 per file.**
   - **Folder:** the subfolder below the one picked.
   - **Department:** by embedding, only with a 0.02 lead over the next; 11/11 on the sample.
   - **Kind:** filename and text keywords first, because embedding alone got only 7/11; embedding as the fallback.
   - **Validity:** `qN-YYYY` and the most common year.
   - A spelling the library already uses is preferred.

**What the user decides.** Every file's shelf, inclusion and tags, and every new shelf's name. The confirm step re-validates all of them (valid and unique names, active shelves, batch analysed) before creating anything.

## Consequences

- One more job type and one more staging area. Staged files count toward disk use until they are confirmed, cancelled or expire.
- The department and kind vocabularies are fixed English lists in `app/ingest/intake.py`. A library on other topics gets fewer department tags and falls back to the closest department for its audience. Making the vocabulary editable is a possible later step.
- The thresholds come from one small corpus. They are constants with comments, to be revisited with the Phase 7 evaluation set.
- `POST /api/documents` with an explicit shelf still works (CLI, e2e kit). The UI now goes through intake.
