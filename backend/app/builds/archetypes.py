from __future__ import annotations

import json
import re
from functools import lru_cache

from ..config import BACKEND_DIR

ARCHETYPES_PATH = BACKEND_DIR / "data" / "archetypes.json"


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


@lru_cache(maxsize=1)
def load_archetypes() -> dict:
    if not ARCHETYPES_PATH.exists():
        return {}
    data = json.loads(ARCHETYPES_PATH.read_text(encoding="utf-8"))
    return {_normalize(k): v for k, v in data.get("by_exotic", {}).items()}


def find_archetype(exotic_name: str) -> dict | None:
    archetypes = load_archetypes()
    norm = _normalize(exotic_name)
    if norm in archetypes:
        return archetypes[norm]
    for key, value in archetypes.items():
        if key in norm or norm in key:
            return value
    return None
