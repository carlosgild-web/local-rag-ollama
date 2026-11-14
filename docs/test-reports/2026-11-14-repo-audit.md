# Repository audit: secrets and personal data (2026-11-14)

Phase 9 asks for an audit of the repo, git history included, before the 1.0 release. These checks covered every commit on every branch (`git log --all`), not just the current files.

## What was checked

| Check | How | Result |
|---|---|---|
| Sensitive files ever committed | every file name ever added, matched against `.env`, `*.db`, `*.sqlite`, keys, `auth.json`, `data/`, model weights (`.gguf`, `.safetensors`, `.onnx`) | none |
| Secrets in any diff | patterns for AWS keys, GitHub tokens, OpenAI-style `sk-` keys, Google API keys, Slack tokens, Hugging Face tokens and private key headers | none |
| Personal data in any diff | e-mail addresses at public mail providers, Windows and macOS home folder paths, machine names (`LAPTOP-…`, `DESKTOP-…`), local project paths, private IP addresses, phone-number shapes | none (the only number matches were port lists) |
| Personal data in images | Tesseract OCR of all 88 image versions in the history, plus a frame every 2 s of the intake GIF, searched for the same patterns | none |
| GitHub alerts | secret scanning, Dependabot and code scanning (CodeQL) | 0 secret, 0 Dependabot; 1 CodeQL alert, fixed below |
| `.gitignore` | covers `data/`, `inbox/`, `.env*` (except `.env.example`), the venv, coverage files, `node_modules`, `dist` | OK |

## Findings

1. **CodeQL `py/stack-trace-exposure` (medium) in `/health`.** `/health` stays open when a password is set (decision 0026), and it returned exception messages, which can hold file paths or addresses. Now, with a password on, a caller who isn't signed in gets only the error type (`ConnectError (sign in for details)`). Without a password nothing changes, since every route is open then anyway. The full message still goes to the log and to the troubleshooter, which needs a session. Tested in `test_health_hides_error_messages_from_signed_out_callers`.
2. **Commit author e-mail.** The first 120 commits carry the author's personal e-mail address. Later ones use the GitHub `noreply` address, as does the current git config. The repository was already public. Rewriting public history would break the tags, the releases and any clones, and copies of the old history may exist anyway. The owner chose to leave the history as it is.

## Not covered

- Files outside git, such as the GitHub Pages site, which is built from `docs/` and so covered above, and the release assets, which are built by CI from tagged commits.
- Text inside PDFs and Word files in `backend/demo/`. Those are the fictional Hilda & Luna documents, written for the demo.
