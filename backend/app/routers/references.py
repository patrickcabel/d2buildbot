from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..bungie import manifest
from ..references import ingest, store

router = APIRouter(prefix="/api/references", tags=["references"])


class IngestBody(BaseModel):
    url: str


@router.get("")
async def list_references() -> dict:
    return {"references": store.list_references()}


@router.get("/{ref_id}")
async def get_reference(ref_id: int) -> dict:
    ref = store.get_reference(ref_id)
    if ref is None:
        raise HTTPException(404, "Reference not found.")
    return ref


@router.post("")
async def add_reference(body: IngestBody) -> dict:
    if manifest.stored_version() is None:
        raise HTTPException(409, "Manifest not synced yet. Sync the manifest first.")
    url = body.url.strip()
    if not url.startswith("http"):
        raise HTTPException(400, "Please provide a full http(s) URL.")
    return await ingest.ingest(url)


@router.post("/{ref_id}/refresh")
async def refresh_reference(ref_id: int) -> dict:
    ref = store.get_reference(ref_id)
    if ref is None:
        raise HTTPException(404, "Reference not found.")
    return await ingest.ingest(ref["url"])


@router.delete("/{ref_id}")
async def delete_reference(ref_id: int) -> dict:
    store.delete_reference(ref_id)
    return {"ok": True}
