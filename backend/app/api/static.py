"""Serves the built React app from the same process (PLAN.md Phase 4).

Files under the build folder are served as they are. Any other GET outside
/api returns index.html, so a browser refresh on /chat/3 still loads the app
and React Router picks the page.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

BACKEND_DIR = Path(__file__).resolve().parents[2]
# Docker copies the build to backend/static; locally it is frontend/dist.
CANDIDATES = (BACKEND_DIR / "static", BACKEND_DIR.parent / "frontend" / "dist")


def find_static_dir(configured: Path | None) -> Path | None:
    for candidate in (configured,) if configured else CANDIDATES:
        if candidate is not None and (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


def mount_frontend(app: FastAPI, static_dir: Path, *, api_prefix: str) -> None:
    index = static_dir / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == api_prefix.strip("/") or path.startswith(api_prefix.strip("/") + "/"):
            raise HTTPException(status_code=404, detail="Not Found")
        target = (static_dir / path).resolve()
        if path and target.is_file() and target.is_relative_to(static_dir):
            # Hashed bundles never change; index.html must always be fresh.
            cache = (
                "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            )
            return FileResponse(target, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
