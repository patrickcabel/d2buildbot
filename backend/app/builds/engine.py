from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

from rapidfuzz import fuzz

from ..bungie import manifest
from ..references import store as ref_store
from . import archetypes as arch
from .wishlist import load_wishlist

WEAPON_SLOTS = ["kinetic", "energy", "power"]
ARMOR_SLOTS = ["helmet", "gauntlets", "chest", "legs", "class"]
CLASS_NAMES = {0: "titan", 1: "hunter", 2: "warlock"}
CLASS_IDS = {"titan": 0, "hunter": 1, "warlock": 2}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def resolve_exotic(query: str) -> Optional[dict]:
    norm_q = f" {_normalize(query)} "
    exotics = manifest.exotic_names()

    # Prefer the longest exact word-boundary name match.
    substring_hits = [
        e for e in exotics if len(e["normalized"]) >= 4 and f" {e['normalized']} " in norm_q
    ]
    if substring_hits:
        return max(substring_hits, key=lambda e: len(e["normalized"]))

    # Fall back to fuzzy matching.
    best, best_score = None, 0
    for e in exotics:
        score = fuzz.token_set_ratio(e["normalized"], norm_q)
        if score > best_score:
            best, best_score = e, score
    return best if best_score >= 80 else None


def _infer_class(query: str, exotic: Optional[dict]) -> Optional[int]:
    if exotic and exotic["entity_type"] == "armor" and exotic["class_type"] in CLASS_NAMES:
        return exotic["class_type"]
    norm_q = _normalize(query)
    for name, cid in CLASS_IDS.items():
        if name in norm_q:
            return cid
    return None


def _wishlist_info(item: dict) -> dict:
    wl = load_wishlist()
    return wl.score(item.get("itemHash"), item.get("perks") or [])


def _score_weapon(item: dict, recommended: set[int]) -> tuple[float, dict]:
    info = _wishlist_info(item)
    score = 0.0
    if item["itemHash"] in recommended:
        score += 100
    if info["is_wishlisted"]:
        score += 60
    score += info["matched_perks"] * 8
    score += (item.get("power") or 0) / 1000.0
    return score, info


def _pick_weapons(items: list[dict], exotic: Optional[dict], recommended: set[int]) -> dict:
    weapons = [i for i in items if i.get("kind") == "weapon" and i.get("slot")]
    exotic_is_weapon = bool(exotic and exotic["entity_type"] == "weapon")
    exotic_hash = exotic["hash"] if exotic else None

    chosen: dict[str, Optional[dict]] = {s: None for s in WEAPON_SLOTS}

    if exotic_is_weapon:
        owned_exotic = next((w for w in weapons if w["itemHash"] == exotic_hash), None)
        exotic_slot = owned_exotic["slot"] if owned_exotic else None
        if exotic_slot:
            info = _wishlist_info(owned_exotic)
            chosen[exotic_slot] = {**owned_exotic, "reason": "Requested exotic", "wishlist": info}

    for slot in WEAPON_SLOTS:
        if chosen[slot] is not None:
            continue
        candidates = [w for w in weapons if w["slot"] == slot]
        if exotic_is_weapon:
            candidates = [w for w in candidates if not w.get("isExotic")]
        if not candidates:
            continue
        ranked = sorted(candidates, key=lambda w: _score_weapon(w, recommended)[0], reverse=True)
        best = ranked[0]
        score, info = _score_weapon(best, recommended)
        reason = "God roll (wishlist)" if info["is_wishlisted"] else None
        if best["itemHash"] in recommended:
            reason = "Recommended by references"
        chosen[slot] = {**best, "reason": reason or "Best available", "wishlist": info}

    return chosen


def _pick_armor(items: list[dict], exotic: Optional[dict], class_type: Optional[int]) -> dict:
    armor = [i for i in items if i.get("kind") == "armor" and i.get("slot")]
    if class_type is not None:
        armor = [a for a in armor if a.get("classType") in (CLASS_NAMES.get(class_type), "unknown")]

    exotic_is_armor = bool(exotic and exotic["entity_type"] == "armor")
    exotic_hash = exotic["hash"] if exotic else None
    chosen: dict[str, Optional[dict]] = {s: None for s in ARMOR_SLOTS}

    if exotic_is_armor:
        owned = next((a for a in armor if a["itemHash"] == exotic_hash), None)
        if owned and owned.get("slot"):
            chosen[owned["slot"]] = {**owned, "reason": "Requested exotic"}

    for slot in ARMOR_SLOTS:
        if chosen[slot] is not None:
            continue
        candidates = [a for a in armor if a["slot"] == slot and not a.get("isExotic")]
        if not candidates:
            continue
        best = max(candidates, key=lambda a: (a.get("power") or 0))
        chosen[slot] = {**best, "reason": "Highest power legendary"}

    return chosen


def _kb_section(anchor: list[int], entity_type: str, limit: int = 6) -> list[dict]:
    facts = ref_store.co_mentioned_facts(anchor, [entity_type])
    return facts[:limit]


def _owned_hashes(items: list[dict]) -> set[int]:
    return {i["itemHash"] for i in items}


def _dim_links(weapons: dict, armor: dict, exotic: Optional[dict]) -> Optional[dict]:
    """Build a DIM search string (and URL) that highlights the build's gear."""
    hashes: list[int] = []
    for slot_item in list(weapons.values()) + list(armor.values()):
        if slot_item and slot_item.get("itemHash"):
            hashes.append(slot_item["itemHash"])
    if exotic and exotic.get("hash"):
        hashes.append(exotic["hash"])
    hashes = list(dict.fromkeys(hashes))  # dedupe, preserve order
    if not hashes:
        return None
    search = " or ".join(f"hash:{h}" for h in hashes)
    url = "https://app.destinyitemmanager.com/inventory?search=" + quote(search)
    return {"search": search, "url": url}


def generate_build(query: str, profile: dict) -> dict:
    items = profile.get("items", [])
    exotic = resolve_exotic(query)
    exotic_name = exotic["name"] if exotic else None
    archetype = arch.find_archetype(exotic_name) if exotic_name else None
    class_type = _infer_class(query, exotic)

    anchor = [exotic["hash"]] if exotic else []

    kb_weapons = _kb_section(anchor, "weapon")
    kb_mods = _kb_section(anchor, "mod")
    kb_fragments = _kb_section(anchor, "fragment")
    kb_aspects = _kb_section(anchor, "aspect")
    kb_subclass = _kb_section(anchor, "subclass")
    kb_sources = ref_store.references_mentioning(anchor)

    recommended_weapon_hashes = {f["manifest_hash"] for f in kb_weapons}

    weapons = _pick_weapons(items, exotic, recommended_weapon_hashes)
    armor = _pick_armor(items, exotic, class_type)

    owned = _owned_hashes(items)
    exotic_owned = bool(exotic and exotic["hash"] in owned)

    # Build recommendation lists (name + owned flag), preferring KB then archetype.
    def merge_named(kb_facts: list[dict], arch_names: Optional[list[str]]) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for f in kb_facts:
            key = f["name"].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "name": f["name"],
                    "hash": f["manifest_hash"],
                    "sources": f.get("sources", 0),
                    "owned": f["manifest_hash"] in owned,
                    "from": "references",
                }
            )
        for name in arch_names or []:
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append({"name": name, "hash": None, "sources": 0, "owned": None, "from": "curated"})
        return out

    subclass = None
    if archetype and archetype.get("element"):
        subclass = archetype["element"]
    elif kb_subclass:
        subclass = kb_subclass[0]["name"]

    rationale = _build_rationale(query, exotic, exotic_owned, archetype, kb_sources)

    references = []
    for src in kb_sources:
        references.append(
            {"url": src["url"], "title": src.get("title") or src["url"], "type": src["source_type"]}
        )
    for url in (archetype or {}).get("references", []):
        if not any(r["url"] == url for r in references):
            references.append({"url": url, "title": url, "type": "curated"})

    return {
        "query": query,
        "matched": exotic is not None,
        "exotic": {
            "name": exotic_name,
            "hash": exotic["hash"] if exotic else None,
            "type": exotic["entity_type"] if exotic else None,
            "owned": exotic_owned,
        }
        if exotic
        else None,
        "classType": CLASS_NAMES.get(class_type) if class_type is not None else "any",
        "subclass": subclass,
        "weapons": weapons,
        "armor": armor,
        "aspects": merge_named(kb_aspects, (archetype or {}).get("aspects")),
        "fragments": merge_named(kb_fragments, (archetype or {}).get("fragments")),
        "mods": merge_named(kb_mods, (archetype or {}).get("mods")),
        "statPriority": (archetype or {}).get("stat_priority", []),
        "rationale": rationale,
        "references": references,
        "notes": (archetype or {}).get("notes"),
        "dim": _dim_links(weapons, armor, exotic),
    }


def _build_rationale(
    query: str,
    exotic: Optional[dict],
    exotic_owned: bool,
    archetype: Optional[dict],
    sources: list[dict],
) -> str:
    if not exotic:
        return (
            "Could not confidently match an exotic to your query. Try naming the exotic "
            "directly, e.g. 'Telesto build'."
        )
    parts = [f"Built around {exotic['name']} ({exotic['entity_type']})."]
    parts.append("You own this exotic." if exotic_owned else "You do NOT own this exotic yet.")
    if archetype:
        parts.append("Used a curated synergy profile for this exotic.")
    if sources:
        parts.append(f"Cross-referenced {len(sources)} saved source(s) from your knowledge base.")
    else:
        parts.append(
            "No saved references mention this exotic yet - add some on the References page "
            "to sharpen recommendations."
        )
    return " ".join(parts)
