# Test corpus

24 short documents written for this project, used to exercise ingestion,
chunking, and retrieval. No copyrighted or personal material — all text
here was authored for this repo and may be freely used and redistributed
under the project's license.

- 12 English, 12 Spanish, covering the same 12 topics so retrieval can be
  compared across languages against a multilingual embedding model.
- 6 topics per language as Markdown (`.md`) with heading structure, to
  test the structure-aware chunker; 6 as plain prose (`.txt`).
- `.docx` / `.pdf` samples will be added in Phase 1 alongside the parser
  dependencies (`python-docx`, `PyMuPDF`).
