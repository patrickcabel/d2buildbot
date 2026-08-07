from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..bungie import client, manifest, profile as profile_svc
from ..builds import engine

router = APIRouter(prefix="/api/builds", tags=["builds"])


class BuildQuery(BaseModel):
    query: str


@router.post("")
async def create_build(body: BuildQuery) -> dict:
    query = body.query.strip()
    if not query:
        raise HTTPException(400, "Query is empty.")
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet. Sync the manifest first.")
    try:
        _, resp = await profile_svc.get_profile_raw()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    profile = profile_svc.normalize_profile(resp)
    return engine.generate_build(query, profile)
