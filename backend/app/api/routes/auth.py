"""Signing in when the app has a password (decision 0026). Without one,
`status` says so and every route is open, as before."""

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import RuntimeDep
from app.api.schemas import AuthStatusOut, LoginIn
from app.core import auth

router = APIRouter(prefix="/auth", tags=["auth"])


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _secure(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or forwarded.split(",")[0].strip() == "https"


@router.get("/status", response_model=AuthStatusOut)
def auth_status(request: Request, runtime: RuntimeDep):
    settings = runtime.settings
    on = auth.enabled(settings)
    token = request.cookies.get(auth.COOKIE_NAME)
    return AuthStatusOut(enabled=on, signed_in=(not on) or auth.valid_session(settings, token))


@router.post("/login", response_model=AuthStatusOut)
def login(request: Request, runtime: RuntimeDep, body: LoginIn):
    """Sets the session cookie. 401 for a wrong password; 429 after 5 wrong
    tries from one address in 5 minutes."""
    settings = runtime.settings
    if not auth.enabled(settings):
        return AuthStatusOut(enabled=False, signed_in=True)
    limiter: auth.LoginLimiter = request.app.state.login_limiter
    client = _client(request)
    wait = limiter.retry_after(client)
    if wait:
        return JSONResponse(
            {"detail": f"too many wrong passwords; try again in {wait} s"},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(wait)},
        )
    if not auth.check_password(settings, body.password):
        limiter.failed(client)
        return JSONResponse({"detail": "wrong password"}, status_code=status.HTTP_401_UNAUTHORIZED)
    limiter.succeeded(client)
    response = JSONResponse(AuthStatusOut(enabled=True, signed_in=True).model_dump())
    cookie = auth.session_cookie(auth.new_session(settings), settings, secure=_secure(request))
    response.headers.append("set-cookie", cookie)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout():
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers.append("set-cookie", auth.cleared_cookie())
    return response
