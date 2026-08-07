from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..bungie import client, manifest, profile as profile_svc
from ..bungie import armor_dupes


router = APIRouter(prefix="/api", tags=["profile"])


@router.post("/manifest/sync")
async def sync_manifest(force: bool = False) -> dict:
    try:
        return await manifest.sync_manifest(force=force)
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface real sync failures to the UI
        raise HTTPException(500, f"Manifest sync failed: {exc}") from exc


@router.get("/manifest/status")
async def manifest_status() -> dict:
    return {"version": manifest.stored_version()}


@router.get("/profile")
async def get_profile() -> dict:
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet. Call /api/manifest/sync first.")
    try:
        membership, normalized, _raw = await profile_svc.get_profile_bundle_cached()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"membership": membership, **normalized}


@router.get("/profile/characters")
async def get_characters() -> dict:
    """Fast character list for build filters (skips full inventory enrich)."""
    try:
        membership, characters = await profile_svc.get_characters_fast()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {
        "membership": membership,
        "characters": characters,
    }


@router.get("/profile/armor-dupes")
async def get_armor_dupes() -> dict:
    """Scan inventory for Armor 3.0 pieces with identical base stat distributions."""
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet. Call /api/manifest/sync first.")
    try:
        return await armor_dupes.scan_armor_dupes()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Armor dupe scan failed: {exc}") from exc


@router.get("/profile/vault-clean")
async def get_vault_clean() -> dict:
    """Scan for armor + weapon duplicates (vault cleaning)."""
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet. Call /api/manifest/sync first.")
    try:
        return await armor_dupes.scan_vault_clean()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Vault clean scan failed: {exc}") from exc


@router.get("/profile/item/{instance_id}")
async def get_item_detail(instance_id: str, itemHash: int | None = None) -> dict:
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet. Call /api/manifest/sync first.")
    try:
        return await profile_svc.get_item_detail(instance_id, item_hash=itemHash)
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
