from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from ..bungie import manifest
from ..config import get_settings
from . import extract, store

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
DIM_HOSTS = {"dim.gg", "app.destinyitemmanager.com", "beta.destinyitemmanager.com"}


def classify_source(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host in YOUTUBE_HOSTS:
        return "youtube"
    if host in DIM_HOSTS:
        return "dim"
    return "web"


def _youtube_video_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        return parsed.path.lstrip("/") or None
    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0]
    match = re.search(r"/(shorts|embed)/([\w-]+)", parsed.path)
    return match.group(2) if match else None


async def _oembed_title(url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://www.youtube.com/oembed", params={"url": url, "format": "json"}
            )
        if resp.status_code == 200:
            return resp.json().get("title")
    except Exception:  # noqa: BLE001
        return None
    return None


def _fetch_transcript(video_id: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        chunks = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(c.get("text", "") for c in chunks)
    except Exception:  # noqa: BLE001
        return ""


async def _fetch_comments(video_id: str, max_comments: int = 100) -> list[str]:
    settings = get_settings()
    if not settings.youtube_api_key:
        return []
    comments: list[str] = []
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": 100,
        "order": "relevance",
        "textFormat": "plainText",
        "key": settings.youtube_api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://www.googleapis.com/youtube/v3/commentThreads", params=params
            )
            if resp.status_code != 200:
                return []
            for item in resp.json().get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comments.append(snippet.get("textDisplay", ""))
                if len(comments) >= max_comments:
                    break
    except Exception:  # noqa: BLE001
        return comments
    return comments


async def _ingest_youtube(url: str) -> dict:
    video_id = _youtube_video_id(url)
    if not video_id:
        return {"title": None, "text": "", "meta": {}, "error": "Could not parse video id."}
    title = await _oembed_title(url)
    transcript = _fetch_transcript(video_id)
    comments = await _fetch_comments(video_id)
    text = transcript + "\n" + "\n".join(comments)
    meta = {
        "video_id": video_id,
        "has_transcript": bool(transcript),
        "comment_count": len(comments),
        "comments": comments[:50],
    }
    error = None
    if not transcript and not comments:
        error = "No transcript or comments retrieved (captions disabled and/or no YOUTUBE_API_KEY)."
    return {"title": title, "text": text, "meta": meta, "error": error}


async def _fetch_html(url: str) -> tuple[Optional[str], str]:
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (D2BuildMaker)"})
        resp.raise_for_status()
        html = resp.text
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return title, text


async def _ingest_web(url: str) -> dict:
    try:
        title, text = await _fetch_html(url)
    except Exception as exc:  # noqa: BLE001
        return {"title": None, "text": "", "meta": {}, "error": f"Fetch failed: {exc}"}
    return {"title": title, "text": text, "meta": {"chars": len(text)}, "error": None}


async def _ingest_dim(url: str) -> dict:
    """Best-effort DIM loadout ingestion.

    Tries the DIM loadout-share API to pull exact item hashes; falls back to
    generic page text extraction.
    """
    share_id = None
    host = (urlparse(url).hostname or "").lower()
    if host == "dim.gg":
        parts = [p for p in urlparse(url).path.split("/") if p]
        if parts:
            share_id = parts[0]

    direct_facts: list[dict] = []
    meta: dict = {}
    if share_id:
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(
                    "https://api.destinyitemmanager.com/loadout_share",
                    params={"shareId": share_id},
                    headers={"X-API-Key": "dim-build-maker", "X-App-Name": "d2-build-maker"},
                )
            if resp.status_code == 200:
                loadout = resp.json().get("loadout") or resp.json()
                meta["loadout"] = loadout
                direct_facts = _facts_from_loadout(loadout)
        except Exception:  # noqa: BLE001
            pass

    web = await _ingest_web(url)
    web["meta"].update(meta)
    web["_direct_facts"] = direct_facts
    return web


def _facts_from_loadout(loadout: dict) -> list[dict]:
    facts: dict[int, dict] = {}
    equipped = loadout.get("equipped", []) if isinstance(loadout, dict) else []
    for entry in equipped:
        h = entry.get("hash") or entry.get("id")
        if not h:
            continue
        row = manifest.name_row(int(h))
        if not row:
            continue
        facts[row["hash"]] = {
            "entity_type": row["entity_type"],
            "manifest_hash": row["hash"],
            "name": row["name"],
            "mention_count": 3,  # equipped items are a strong signal
            "snippet": "From DIM loadout",
        }
    return list(facts.values())


async def ingest(url: str) -> dict:
    source_type = classify_source(url)
    ref_id = store.upsert_reference(source_type, url)

    if source_type == "youtube":
        result = await _ingest_youtube(url)
    elif source_type == "dim":
        result = await _ingest_dim(url)
    else:
        result = await _ingest_web(url)

    text = result.get("text") or ""
    facts = extract.extract_facts(text)

    # Merge any direct (hash-based) facts from DIM loadouts.
    for direct in result.get("_direct_facts", []):
        existing = next((f for f in facts if f["manifest_hash"] == direct["manifest_hash"]), None)
        if existing:
            existing["mention_count"] += direct["mention_count"]
        else:
            facts.append(direct)

    status = "error" if (result.get("error") and not facts) else "ready"
    store.set_reference_result(
        ref_id,
        title=result.get("title"),
        raw_text=text[:200000] if text else None,
        raw_meta=result.get("meta"),
        status=status,
        error=result.get("error"),
    )
    store.replace_facts(ref_id, facts)
    return store.get_reference(ref_id)
