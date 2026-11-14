# Security

## What this project is

A **local, single-user demo** of a retrieval-augmented generation (RAG) app. It's built to run on your own computer next to Ollama.

- **No sign-in by default, an optional password.** Out of the box the console, the employee intranet and the API are open to anyone who can reach the server ([decision 0010](docs/decisions/0010-employee-portal.md), [decision 0011](docs/decisions/0011-public-site.md)). The public site's "staff sign-in" is a simulation and says so. `python -m app.cli set-password` (or `APP_PASSWORD`) puts one password in front of the console, the intranet and every API route. It's a single shared password, not user accounts ([decision 0026](docs/decisions/0026-optional-password.md)).
- **Run it locally or on a private network.** Set a password before anyone else can reach it, and never expose it to the internet as it is: there is no TLS of its own, so put it behind a reverse proxy that adds HTTPS. Docker Compose publishes its ports on `127.0.0.1` only, and the container runs as a non-root user.
- **No cloud calls at runtime.** Models run in Ollama; fonts and images are bundled; Chroma's telemetry is turned off.

## How the code protects itself

- Uploads have a size limit and an extension allow-list. Client-supplied paths are reduced to a bare file name, and stored files are named by their SHA-256.
- Intake batch ids must be 32 hex characters; the static file server only serves files inside its build folder.
- All SQL uses bound parameters, and keyword search builds its own FTS5 query from the user's words.
- The model is told to answer only from the retrieved passages. The end-to-end kit includes prompt-injection checks.
- CI runs with read-only permissions, and Dependabot proposes dependency updates weekly.

## Known advisories that don't apply

`pip-audit` (2026-11-09) reports advisories against **chromadb 1.5.9** with no fixed release yet: CVE-2026-45829, CVE-2026-45830, CVE-2026-45831 and CVE-2026-45833. All of them are in **Chroma's HTTP server** (its `/api/v2` endpoints and authorization providers). This app uses Chroma only **embedded** (`PersistentClient`): the server is never started, and embeddings are computed by Ollama, so the vulnerable code isn't reachable. Dependabot will propose the update once Chroma ships a fix.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting**: the *Security* tab, then *Report a vulnerability*. Don't open a public issue. In scope: anything that lets a request read or write outside `DATA_DIR`, run code, or reach the network from the app. With the password on, a way to use the API without signing in is in scope. With it off, open access is by design.
