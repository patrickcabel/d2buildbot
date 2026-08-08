from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import BACKEND_DIR, get_settings
from .db import init_db
from .routers import actions, auth, builds, profile, references, wishlists

log = logging.getLogger("d2build")


def _find_static_dir() -> Path | None:
    candidates: list[Path] = []
    env = (os.environ.get("STATIC_DIR") or "").strip()
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            BACKEND_DIR / "static",
            Path("/app/backend/static"),
            Path("/app/static"),
        ]
    )
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        index = path / "index.html"
        if path.is_dir() and index.is_file():
            return path
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    static = _find_static_dir()
    log.warning("static_dir=%s exists=%s", static, static is not None)
    yield


app = FastAPI(title="D2 Build Maker", lifespan=lifespan)

settings = get_settings()
origins = {settings.resolved_frontend_origin}
public = settings.resolved_bungie_redirect_uri.rsplit("/api/", 1)[0]
if public:
    origins.add(public)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .session import session_middleware  # noqa: E402

app.middleware("http")(session_middleware)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(references.router)
app.include_router(builds.router)
app.include_router(wishlists.router)
app.include_router(actions.router)

_static = _find_static_dir()


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "static": _static is not None,
        "staticDir": str(_static) if _static else None,
    }


if _static is not None:
    assets = _static / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/")
    async def spa_index() -> FileResponse:
        return FileResponse(_static / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        # Never shadow API routes (defense in depth).
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (_static / full_path).resolve()
        try:
            candidate.relative_to(_static.resolve())
        except ValueError as exc:
            raise HTTPException(404, "Not found") from exc
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_static / "index.html")
else:
    @app.get("/")
    async def missing_ui() -> dict:
        return {
            "ok": False,
            "error": "Frontend static files missing from this deploy.",
            "hint": "Rebuild the Docker image; /app/backend/static/index.html should exist.",
        }
