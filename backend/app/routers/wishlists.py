from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from ..builds import wishlist
from ..bungie import profile as profile_svc

router = APIRouter(prefix="/api/wishlists", tags=["wishlists"])

VOLTRON_URL = (
    "https://raw.githubusercontent.com/48klocs/dim-wish-list-sources/master/voltron.txt"
)


@router.get("/status")
async def status() -> dict:
    return wishlist.wishlist_stats()


@router.post("/download-voltron")
async def download_voltron() -> dict:
    wishlist.WISHLIST_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(VOLTRON_URL)
            resp.raise_for_status()
            content = resp.text
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Failed to download voltron.txt: {exc}") from exc

    target = wishlist.WISHLIST_DIR / "voltron.txt"
    target.write_text(content, encoding="utf-8")
    stats = wishlist.reload_wishlist()
    profile_svc.invalidate_all_profile_caches()
    return {
        "ok": True,
        "bytes": len(content.encode("utf-8")),
        "items": len(stats.rolls),
        "rolls": sum(len(v) for v in stats.rolls.values()),
    }


@router.post("/reload")
async def reload() -> dict:
    wishlist.reload_wishlist()
    profile_svc.invalidate_all_profile_caches()
    return wishlist.wishlist_stats()
