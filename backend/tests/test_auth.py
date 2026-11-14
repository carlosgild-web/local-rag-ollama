"""The optional password (decision 0026): off by default, and when it's on,
every API route needs a session except signing in and the health check."""

import pytest
from fastapi.testclient import TestClient

from app import cli
from app.core import auth
from app.main import create_app

PASSWORD = "correct horse battery"


@pytest.fixture
def client(runtime):
    app = create_app(runtime, start_worker=False)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def locked(runtime):
    auth.set_password(runtime.settings, PASSWORD)
    return runtime


def _login(client, password=PASSWORD):
    return client.post("/api/auth/login", json={"password": password})


# --- Off by default ----------------------------------------------------------------


def test_without_a_password_everything_is_open(client):
    assert client.get("/api/auth/status").json() == {"enabled": False, "signed_in": True}
    assert client.get("/api/documents").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert _login(client, "anything").json() == {"enabled": False, "signed_in": True}


# --- With a password ---------------------------------------------------------------


def test_the_api_needs_a_session(client, locked):
    assert client.get("/api/auth/status").json() == {"enabled": True, "signed_in": False}
    for path in ("/api/documents", "/api/collections", "/api/audit", "/openapi.json", "/docs"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json() == {"detail": "sign in first"}
    assert client.post("/api/chat", json={"question": "hi"}).status_code == 401
    assert client.get("/health").status_code in (200, 503), "the health check stays open"
    assert client.get("/api/health").status_code in (200, 503)


def test_signing_in_and_out(client, locked):
    assert _login(client, "wrong password").status_code == 401
    response = _login(client)
    assert response.status_code == 200 and response.json()["signed_in"] is True
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Secure" not in cookie
    assert client.get("/api/documents").status_code == 200
    assert client.get("/api/auth/status").json() == {"enabled": True, "signed_in": True}

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/documents").status_code == 401


def test_https_cookies_are_secure(client, locked):
    response = client.post(
        "/api/auth/login", json={"password": PASSWORD}, headers={"X-Forwarded-Proto": "https"}
    )
    assert "Secure" in response.headers["set-cookie"]


def test_changing_or_clearing_the_password_ends_sessions(client, locked):
    _login(client)
    auth.set_password(locked.settings, "a different password")
    assert client.get("/api/documents").status_code == 401
    _login(client, "a different password")
    assert client.get("/api/documents").status_code == 200
    auth.clear_password(locked.settings)
    assert client.get("/api/auth/status").json() == {"enabled": False, "signed_in": True}


def test_the_env_var_wins_over_the_stored_hash(client, locked):
    locked.settings.app_password = "from the environment"
    assert _login(client, PASSWORD).status_code == 401
    assert _login(client, "from the environment").status_code == 200
    assert client.get("/api/documents").status_code == 200


def test_too_many_wrong_passwords_are_refused_for_a_while(client, locked):
    for _ in range(5):
        assert _login(client, "nope").status_code == 401
    refused = _login(client)  # even the right one, until the window passes
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) > 0


def test_forged_tampered_and_expired_sessions_are_refused(locked):
    settings = locked.settings
    token = auth.new_session(settings)
    assert auth.valid_session(settings, token)
    body, signature = token.rsplit(".", 1)
    assert not auth.valid_session(settings, f"{body}x.{signature}")
    assert not auth.valid_session(settings, f"{body}.{signature[:-2]}AA")
    assert not auth.valid_session(settings, "not-a-token")
    assert not auth.valid_session(settings, None)
    late = 1e12  # far in the future
    assert not auth.valid_session(settings, token, now=late)


# --- Passwords, the limiter and the CLI -------------------------------------------


def test_password_hashes_are_salted_and_verify():
    a, b = auth.hash_password("s3cret pass"), auth.hash_password("s3cret pass")
    assert a != b and a.startswith("scrypt$")
    assert auth.verify_password("s3cret pass", a)
    assert not auth.verify_password("other", a)
    assert not auth.verify_password("s3cret pass", "md5$garbage")
    with pytest.raises(auth.AuthError):
        auth.hash_password("")


def test_short_passwords_are_refused(runtime):
    with pytest.raises(auth.AuthError):
        auth.set_password(runtime.settings, "short")
    assert not auth.enabled(runtime.settings)


def test_the_stored_file_never_holds_the_password(locked):
    text = (locked.settings.data_dir / "auth.json").read_text(encoding="utf-8")
    assert PASSWORD not in text and "scrypt$" in text


def test_limiter_window_and_reset():
    limiter = auth.LoginLimiter(max_failures=2, window=10)
    limiter.failed("a", now=0)
    limiter.failed("a", now=1)
    assert limiter.retry_after("a", now=2) > 0
    assert limiter.retry_after("b", now=2) == 0, "per client address"
    assert limiter.retry_after("a", now=12) == 0, "the window passed"
    limiter.failed("a", now=13)
    limiter.succeeded("a")
    assert limiter.retry_after("a", now=13) == 0


def test_cli_sets_and_clears_the_password(runtime, monkeypatch, capsys):
    from io import StringIO

    monkeypatch.setattr(cli, "get_settings", lambda: runtime.settings)
    monkeypatch.setattr(cli, "build_runtime", lambda _settings: runtime)
    monkeypatch.setattr("sys.stdin", StringIO(PASSWORD + "\n"))
    assert cli.main(["set-password", "--stdin"]) == 0
    assert auth.check_password(runtime.settings, PASSWORD)

    assert cli.main(["clear-password"]) == 0
    assert not auth.enabled(runtime.settings)
    assert cli.main(["clear-password"]) == 0
    assert "No password was stored" in capsys.readouterr().out

    monkeypatch.setattr("sys.stdin", StringIO("short\n"))
    assert cli.main(["set-password", "--stdin"]) == 1

    with runtime.session_factory() as db:
        from app.db.models import AuditLog

        actions = [a.action for a in db.query(AuditLog).all()]
    assert "password_set" in actions and "password_clear" in actions
