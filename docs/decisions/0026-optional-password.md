# 0026: One optional password, standard library only

**Status:** accepted (2026-11-14)

## Context

Phase 8 asks for "optional password auth (localhost-only by default)". Until now the console, the employee portal and the whole API were open to anyone who could reach the server, which was acceptable only because the start scripts and Compose listen on `127.0.0.1`.

The user chose (2026-11-14):
- **one password for the console, the portal and the API.** The portal calls the same `/api/chat` as the console, so leaving it open would leave the API open too.
- **set from the CLI or an environment variable**, with no settings page.

## Decision

- **Off by default.** Without a password nothing changes. `GET /api/auth/status` says `enabled: false`.
- **Where the password comes from:**
  - `python -m app.cli set-password` (or `--stdin` in scripts) stores an **scrypt** hash with a random salt in `DATA_DIR/auth.json`, never the password itself. Fewer than 8 characters is refused.
  - `APP_PASSWORD` works too, for Docker (`compose.yaml` passes it through). It wins when both are set and is compared in constant time.
  - `clear-password` removes the stored hash. Setting and clearing are audited (`password_set`, `password_clear`).
- **Sessions:** after `POST /api/auth/login`, a cookie `rag_session` holds an expiry and a fingerprint of the password, signed with HMAC-SHA256.
  - The key is 32 random bytes in `DATA_DIR/secret_key`.
  - The cookie is `HttpOnly`, `SameSite=Strict` (cross-site requests carry no cookie, which covers CSRF for this app), and `Secure` when the request came over HTTPS (`X-Forwarded-Proto` behind a proxy).
  - It lasts 7 days (`AUTH_SESSION_DAYS`).
  - Changing or clearing the password changes the fingerprint, so everyone is signed out. The fingerprint is scrypt keyed with the server's secret, so a cookie doesn't let anyone test password guesses offline. The first version used a plain SHA-256, and CodeQL flagged it (`py/weak-sensitive-data-hashing`).
  - `POST /api/auth/logout` clears the cookie.
- **What needs a session:** every `/api` route and the API docs (`/docs`, `/redoc`, `/openapi.json`). These stay open:
  - `/health` and `/api/health` (the container health check)
  - the three `/api/auth` routes
  - the static pages, which hold no data: the public `/site`, and the console and portal pages, which then show the sign-in screen

  A pure ASGI middleware checks this on every request, reading the settings each time. That way `set-password` takes effect without a restart, and streamed answers aren't buffered.
- **Wrong passwords:** after 5 from one client address in 5 minutes, sign-in answers 429 with `Retry-After`. The limit is kept in memory, which is enough for one process (the app runs exactly one).
- **Frontend:** an `AuthGate` in front of the console and the portal shows the sign-in screen when needed. Any 401 re-checks the status, so an expired session goes back to sign-in. "Sign out" is in the console's sidebar.
- **No new dependency:** `hashlib.scrypt`, `hmac` and `secrets`. Starlette's `SessionMiddleware` would need `itsdangerous`.

## Not done

- **The start scripts don't refuse to listen beyond localhost without a password.** In Docker the app sees requests from Docker's network, not loopback, so a check in the app can't tell "local" apart. Both routes publish on `127.0.0.1`, and the README and `SECURITY.md` say to set a password before exposing the app.
- **No user accounts or roles.** One shared password. The demo's "staff sign-in" stays a simulation.
- **No TLS of its own.** A reverse proxy adds it.
