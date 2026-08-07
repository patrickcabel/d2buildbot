from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from typing import Optional

from ..bungie import manifest

# Entity types worth matching in free text.
MATCH_TYPES = ["weapon", "armor", "subclass", "aspect", "fragment", "mod", "perk"]

# Common words that also appear as (sub)strings of Destiny item names; ignore
# single-token names matching these to cut down on false positives.
STOPWORD_NAMES = {
    "strand", "void", "solar", "arc", "stasis", "kinetic", "well", "font", "surge",
    "charge", "reload", "loader", "targeting", "unflinching", "dexterity", "holster",
    "grenade", "melee", "super", "class", "health", "weapon", "weapons",
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


@lru_cache(maxsize=1)
def _name_index_cache_key() -> Optional[str]:
    return manifest.stored_version()


def _build_index() -> dict[str, list[tuple[str, int, str, str]]]:
    """Map first-token -> list of (normalized_name, hash, entity_type, display_name)."""
    index: dict[str, list[tuple[str, int, str, str]]] = defaultdict(list)
    for row in manifest.all_names(MATCH_TYPES):
        norm = row["normalized"]
        if len(norm) < 4:
            continue
        tokens = norm.split()
        if len(tokens) == 1 and norm in STOPWORD_NAMES:
            continue
        index[tokens[0]].append((norm, row["hash"], row["entity_type"], row["name"]))
    return index


# Cache the built index per manifest version.
_INDEX: dict = {"version": None, "data": None}


def _get_index() -> dict[str, list[tuple[str, int, str, str]]]:
    version = manifest.stored_version()
    if _INDEX["version"] != version or _INDEX["data"] is None:
        _INDEX["version"] = version
        _INDEX["data"] = _build_index()
    return _INDEX["data"]


def extract_facts(text: str) -> list[dict]:
    """Find Destiny item/perk/etc. names mentioned in text with mention counts."""
    if not text:
        return []
    norm_text = _normalize(text)
    padded = f" {norm_text} "
    tokens = set(norm_text.split())
    index = _get_index()

    found: dict[int, dict] = {}
    for token in tokens:
        for norm_name, hash_, entity, display in index.get(token, []):
            needle = f" {norm_name} "
            count = padded.count(needle)
            if count <= 0:
                continue
            if hash_ in found:
                found[hash_]["mention_count"] += count
            else:
                idx = norm_text.find(norm_name)
                snippet = _snippet(text, norm_text, idx, norm_name)
                found[hash_] = {
                    "entity_type": entity,
                    "manifest_hash": hash_,
                    "name": display,
                    "mention_count": count,
                    "snippet": snippet,
                }
    return sorted(found.values(), key=lambda f: f["mention_count"], reverse=True)


def _snippet(original: str, norm_text: str, norm_idx: int, norm_name: str) -> str:
    if norm_idx < 0:
        return ""
    # Approximate mapping back to original text by ratio.
    ratio = len(original) / max(len(norm_text), 1)
    start = max(0, int(norm_idx * ratio) - 40)
    end = min(len(original), int((norm_idx + len(norm_name)) * ratio) + 40)
    return original[start:end].strip().replace("\n", " ")
