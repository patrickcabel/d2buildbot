from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..bungie import client, manifest, profile as profile_svc

router = APIRouter(prefix="/api", tags=["profile"])


@router.post("/manifest/sync")
async def sync_manifest(force: bool = False) -> dict:
    try:
        return await manifest.sync_manifest(force=force)
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/manifest/status")
async def manifest_status() -> dict:
    return {"version": manifest.stored_version()}


@router.get("/profile")
async def get_profile() -> dict:
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet. Call /api/manifest/sync first.")
    try:
        membership, resp = await profile_svc.get_profile_raw()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    normalized = profile_svc.normalize_profile(resp)
    return {"membership": membership, **normalized}


@router.get("/profile/characters")
async def get_characters() -> dict:
    """Fast character list for build filters (skips full inventory enrich)."""
    try:
        membership, resp = await profile_svc.get_profile_raw()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {
        "membership": membership,
        "characters": profile_svc.extract_characters(resp),
    }


@router.get("/profile/item/{instance_id}")
async def get_item_detail(instance_id: str, itemHash: int | None = None) -> dict:
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet. Call /api/manifest/sync first.")
    try:
        return await profile_svc.get_item_detail(instance_id, item_hash=itemHash)
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
