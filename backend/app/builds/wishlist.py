from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..config import BACKEND_DIR

WISHLIST_DIR = BACKEND_DIR / "data" / "wishlists"

# Matches the DIM wishlist format:
#   dimwishlist:item=<hash>&perks=<hash>,<hash>#notes:<text>
LINE_RE = re.compile(
    r"^dimwishlist:item=(-?\d+)(?:&perks=([\d,]*))?(?:#notes:(.*))?", re.IGNORECASE
)


@dataclass
class WishlistRoll:
    perks: frozenset[int]
    notes: str = ""
    undesirable: bool = False


@dataclass
class Wishlist:
    rolls: dict[int, list[WishlistRoll]] = field(default_factory=dict)

    def score(self, item_hash: int, owned_perks: list[int]) -> dict:
        """Return best god-roll match info for an owned weapon instance."""
        rolls = self.rolls.get(item_hash)
        if not rolls:
            return {
                "is_wishlisted": False,
                "matched_perks": 0,
                "needed_perks": 0,
                "notes": None,
                "tier": "none",
            }
        owned = set(owned_perks or [])
        best = {
            "is_wishlisted": False,
            "matched_perks": 0,
            "needed_perks": 0,
            "notes": None,
            "tier": "none",
        }
        for roll in rolls:
            if roll.undesirable or not roll.perks:
                continue
            needed = len(roll.perks)
            overlap = len(roll.perks & owned)
            if roll.perks.issubset(owned):
                return {
                    "is_wishlisted": True,
                    "matched_perks": needed,
                    "needed_perks": needed,
                    "notes": roll.notes or None,
                    "tier": "god",
                }
            if overlap > best["matched_perks"]:
                # "near" = at least half the wishlist column perks, or 2+.
                near = overlap >= max(2, (needed + 1) // 2)
                best = {
                    "is_wishlisted": False,
                    "matched_perks": overlap,
                    "needed_perks": needed,
                    "notes": roll.notes or None,
                    "tier": "near" if near else "partial",
                }
        return best


@lru_cache(maxsize=1)
def load_wishlist() -> Wishlist:
    wl = Wishlist()
    if not WISHLIST_DIR.exists():
        return wl
    for path in _wishlist_files():
        _parse_file(path, wl)
    return wl


def _wishlist_files() -> list[Path]:
    if not WISHLIST_DIR.exists():
        return []
    return [p for p in sorted(WISHLIST_DIR.glob("*.txt")) if p.name.lower() != "readme.txt"]


def reload_wishlist() -> Wishlist:
    load_wishlist.cache_clear()
    return load_wishlist()


def wishlist_stats() -> dict:
    wl = load_wishlist()
    files = [p.name for p in _wishlist_files()]
    return {
        "items": len(wl.rolls),
        "rolls": sum(len(v) for v in wl.rolls.values()),
        "files": files,
    }


def _parse_file(path: Path, wl: Wishlist) -> None:
    block_notes = ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            block_notes = ""
            continue
        if line.lower().startswith("notes:"):
            block_notes = line[len("notes:"):].strip()
            continue
        if line.lower().startswith(("title:", "description:")):
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        item_hash = int(m.group(1))
        perks = frozenset(
            int(p) for p in (m.group(2) or "").split(",") if p.strip().isdigit()
        )
        notes = (m.group(3) or block_notes or "").strip()
        undesirable = item_hash < 0 and item_hash != -69420
        key = abs(item_hash) if undesirable else item_hash
        wl.rolls.setdefault(key, []).append(
            WishlistRoll(perks=perks, notes=notes, undesirable=undesirable)
        )
