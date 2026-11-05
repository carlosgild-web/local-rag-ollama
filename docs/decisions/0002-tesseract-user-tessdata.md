# 0002 — Per-user tessdata directory for local Windows dev

## Context

Tesseract OCR was installed via winget to `C:\Program Files\Tesseract-OCR`,
which only ships the `eng` language pack. The corpus is English and
Spanish, so `spa.traineddata` is needed too, but writing into
`C:\Program Files\...\tessdata` requires admin elevation we don't have in
this non-interactive shell.

## Decision

Downloaded `spa.traineddata` from the official `tesseract-ocr/tessdata`
repo into a user-writable directory (`%USERPROFILE%\.tessdata`, alongside
a copy of `eng.traineddata`) and point `TESSDATA_PREFIX` at it via
`.env` / `core/config.py` (`tessdata_prefix` setting) instead of the
install directory.

## Consequences

Local Windows dev needs `TESSDATA_PREFIX` (and `TESSERACT_CMD` if
`tesseract.exe` isn't on `PATH`) set in `.env`. Not relevant in Docker —
the `Dockerfile` already installs `tesseract-ocr-eng` and
`tesseract-ocr-spa` system-wide via `apt`, which writes to a location
root owns at build time, so no override is needed there.
