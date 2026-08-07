from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..bungie import client, manifest, profile as profile_svc
from ..builds import armor_solver, engine

router = APIRouter(prefix="/api/builds", tags=["builds"])


class BuildQuery(BaseModel):
    query: str
    classType: Optional[str] = None  # titan | hunter | warlock
    characterId: Optional[str] = None
    statPriority: Optional[list[str]] = Field(default=None)
    includeVault: bool = True


class ArmorSolveBody(BaseModel):
    classType: str
    characterId: Optional[str] = None
    includeVault: bool = True
    exoticHash: Optional[int] = None
    targets: dict[str, int] = Field(default_factory=dict)
    fragmentHashes: list[int] = Field(default_factory=list)
    aspectHashes: list[int] = Field(default_factory=list)
    maxResults: int = 12


class ArmorCapsBody(BaseModel):
    classType: str
    characterId: Optional[str] = None
    includeVault: bool = True
    exoticHash: Optional[int] = None
    targets: dict[str, int] = Field(default_factory=dict)
    fragmentHashes: list[int] = Field(default_factory=list)


@router.post("")
async def create_build(body: BuildQuery) -> dict:
    query = body.query.strip()
    if not query:
        raise HTTPException(400, "Query is empty.")
    if body.classType and body.classType.lower() not in ("titan", "hunter", "warlock"):
        raise HTTPException(400, "classType must be titan, hunter, or warlock.")
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet. Sync the manifest first.")
    try:
        _, resp = await profile_svc.get_profile_raw()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    profile = profile_svc.normalize_profile(resp)
    return engine.generate_build(
        query,
        profile,
        class_type=body.classType.lower() if body.classType else None,
        character_id=body.characterId,
        stat_priority=body.statPriority,
        include_vault=body.includeVault,
    )


@router.get("/exotics")
async def list_exotics(
    classType: str = Query(..., description="titan|hunter|warlock"),
    characterId: Optional[str] = None,
    includeVault: bool = True,
) -> dict:
    if classType.lower() not in ("titan", "hunter", "warlock"):
        raise HTTPException(400, "classType must be titan, hunter, or warlock.")
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet.")
    try:
        profile = await profile_svc.get_normalized_profile_cached()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    items, _ = engine._filter_items_for_character(
        profile.get("items") or [],
        profile.get("characters") or [],
        characterId,
        include_vault=includeVault,
    )
    owned = {
        int(i["itemHash"])
        for i in items
        if i.get("kind") == "armor"
        and i.get("isExotic")
        and i.get("classType") == classType.lower()
    }
    # Also mark owned from full profile so vault-only pieces show when filtered out.
    owned |= armor_solver.owned_exotic_hashes(profile, classType)
    return {
        "classType": classType.lower(),
        "exotics": armor_solver.list_exotic_armor(classType, owned),
    }


@router.get("/subclass-options")
async def subclass_options(
    classType: str = Query(...),
    element: Optional[str] = None,
) -> dict:
    if classType.lower() not in ("titan", "hunter", "warlock"):
        raise HTTPException(400, "classType must be titan, hunter, or warlock.")
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet.")
    return armor_solver.list_subclass_options(classType, element)


@router.post("/stat-caps")
async def armor_stat_caps(body: ArmorCapsBody) -> dict:
    """Max reachable stats from inventory (D2ArmorPicker-style slider caps)."""
    if body.classType.lower() not in ("titan", "hunter", "warlock"):
        raise HTTPException(400, "classType must be titan, hunter, or warlock.")
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet.")
    try:
        profile = await profile_svc.get_normalized_profile_cached()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    try:
        return armor_solver.compute_stat_caps(
            profile,
            class_type=body.classType,
            targets=body.targets,
            exotic_hash=body.exoticHash,
            character_id=body.characterId,
            include_vault=body.includeVault,
            fragment_hashes=body.fragmentHashes,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/solve")
async def solve_armor(body: ArmorSolveBody) -> dict:
    if body.classType.lower() not in ("titan", "hunter", "warlock"):
        raise HTTPException(400, "classType must be titan, hunter, or warlock.")
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet.")
    try:
        profile = await profile_svc.get_normalized_profile_cached()
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    try:
        return armor_solver.solve_armor(
            profile,
            class_type=body.classType,
            targets=body.targets,
            exotic_hash=body.exoticHash,
            character_id=body.characterId,
            include_vault=body.includeVault,
            fragment_hashes=body.fragmentHashes,
            aspect_hashes=body.aspectHashes,
            max_results=min(max(body.maxResults, 1), 25),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
