from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import init_db
from .routers import actions, auth, builds, profile, references, wishlists


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(references.router)
app.include_router(builds.router)
app.include_router(wishlists.router)
app.include_router(actions.router)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


_static: Path | None = settings.resolved_static_dir
if _static is not None:
    assets = _static / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    async def spa_index() -> FileResponse:
        return FileResponse(_static / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(404, "Not found")
        candidate = _static / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_static / "index.html")
