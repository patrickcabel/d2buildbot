from __future__ import annotations

import re
from typing import Any, Optional
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

# Current armor 6-stat system (hashes reused from the legacy names).
ARMOR_STAT_HASHES = {
    "weapons": 2996146975,
    "health": 392767087,
    "class": 1943323491,
    "grenade": 1735777505,
    "super": 144602215,
    "melee": 4244567218,
}
ARMOR_STAT_ORDER = ["weapons", "health", "class", "grenade", "super", "melee"]
# Display labels matching in-game / archetypes.json.
ARMOR_STAT_LABELS = {
    "weapons": "Weapons",
    "health": "Health",
    "class": "Class",
    "grenade": "Grenade",
    "super": "Super",
    "melee": "Melee",
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _normalize_stat_name(name: str) -> Optional[str]:
    key = _normalize(name)
    aliases = {
        "weapons": "weapons",
        "weapon": "weapons",
        "health": "health",
        "class": "class",
        "grenade": "grenade",
        "grenades": "grenade",
        "super": "super",
        "melee": "melee",
        # Legacy names → current system (same hashes).
        "mobility": "weapons",
        "resilience": "health",
        "resil": "health",
        "recovery": "class",
        "discipline": "grenade",
        "intellect": "super",
        "strength": "melee",
    }
    return aliases.get(key)


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


def _class_id_from_name(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    return CLASS_IDS.get(_normalize(name))


def _resolve_class(
    query: str,
    exotic: Optional[dict],
    archetype: Optional[dict],
    explicit_class: Optional[str],
    character_class: Optional[str],
) -> Optional[int]:
    """Resolve guardian class. Character / explicit UI choice win over inference."""
    for candidate in (explicit_class, character_class):
        cid = _class_id_from_name(candidate)
        if cid is not None:
            return cid
    if exotic and exotic["entity_type"] == "armor" and exotic["class_type"] in CLASS_NAMES:
        return exotic["class_type"]
    arch_class = (archetype or {}).get("class")
    if arch_class and arch_class != "any":
        cid = _class_id_from_name(arch_class)
        if cid is not None:
            return cid
    norm_q = _normalize(query)
    for name, cid in CLASS_IDS.items():
        if name in norm_q:
            return cid
    return None


def _filter_items_for_character(
    items: list[dict],
    characters: list[dict],
    character_id: Optional[str],
    include_vault: bool = True,
) -> tuple[list[dict], Optional[str]]:
    """Limit gear to one character (+ vault). Returns (items, character_class)."""
    if not character_id:
        return items, None
    char = next((c for c in characters if c.get("characterId") == character_id), None)
    char_class = char.get("classType") if char else None
    filtered = []
    for i in items:
        if i.get("characterId") == character_id:
            filtered.append(i)
        elif include_vault and i.get("location") == "vault":
            filtered.append(i)
    return filtered, char_class


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


def _armor_stat_value(item: dict, stat_key: str) -> int:
    stats = item.get("stats") or {}
    h = ARMOR_STAT_HASHES[stat_key]
    # Profile stats keys may be str or int depending on JSON path.
    raw = stats.get(h)
    if raw is None:
        raw = stats.get(str(h))
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _score_armor(item: dict, stat_priority: list[str]) -> tuple[float, str]:
    """Weighted sum of preferred stats; power is a light tiebreak."""
    if not stat_priority:
        stat_priority = ["weapons", "health", "class"]
    score = 0.0
    parts: list[str] = []
    weight = 100.0
    for key in stat_priority:
        val = _armor_stat_value(item, key)
        score += val * weight
        parts.append(f"{ARMOR_STAT_LABELS[key]} {val}")
        weight *= 0.45
    # Mild preference for pieces already on the character vs vault.
    if item.get("location") == "equipped":
        score += 3
    elif item.get("location") == "character":
        score += 1
    score += (item.get("power") or 0) * 0.01
    focus = " / ".join(parts[:3]) if parts else "power"
    return score, focus


def _pick_armor(
    items: list[dict],
    exotic: Optional[dict],
    class_type: Optional[int],
    stat_priority: list[str],
) -> dict:
    armor = [i for i in items if i.get("kind") == "armor" and i.get("slot")]
    # Strict class filter — never mix Titan/Hunter/Warlock pieces.
    if class_type is not None:
        target = CLASS_NAMES[class_type]
        armor = [a for a in armor if a.get("classType") == target]
    else:
        # No class resolved → refuse to invent a mixed set.
        return {s: None for s in ARMOR_SLOTS}

    exotic_is_armor = bool(exotic and exotic["entity_type"] == "armor")
    exotic_hash = exotic["hash"] if exotic else None
    chosen: dict[str, Optional[dict]] = {s: None for s in ARMOR_SLOTS}

    if exotic_is_armor:
        # Only pin if the exotic matches this class.
        exotic_class = CLASS_NAMES.get(exotic["class_type"]) if exotic else None
        if exotic_class == CLASS_NAMES[class_type]:
            owned = next((a for a in armor if a["itemHash"] == exotic_hash), None)
            if owned and owned.get("slot"):
                _, focus = _score_armor(owned, stat_priority)
                chosen[owned["slot"]] = {
                    **owned,
                    "reason": f"Requested exotic · {focus}",
                }

    for slot in ARMOR_SLOTS:
        if chosen[slot] is not None:
            continue
        candidates = [a for a in armor if a["slot"] == slot and not a.get("isExotic")]
        if not candidates:
            continue
        ranked = sorted(
            candidates, key=lambda a: _score_armor(a, stat_priority)[0], reverse=True
        )
        best = ranked[0]
        _, focus = _score_armor(best, stat_priority)
        chosen[slot] = {**best, "reason": f"Best for {focus}"}

    return chosen


def _kb_section(anchor: list[int], entity_type: str, limit: int = 6) -> list[dict]:
    facts = ref_store.co_mentioned_facts(anchor, [entity_type])
    return facts[:limit]


def _owned_hashes(items: list[dict]) -> set[int]:
    return {i["itemHash"] for i in items}


def _dim_links(weapons: dict, armor: dict, exotic: Optional[dict]) -> Optional[dict]:
    """Build a DIM search string (and URL) that highlights the build's gear."""
    id_parts: list[str] = []
    hash_parts: list[str] = []
    seen_hashes: set[int] = set()
    for slot_item in list(weapons.values()) + list(armor.values()):
        if not slot_item:
            continue
        iid = slot_item.get("itemInstanceId")
        if iid:
            id_parts.append(f"id:{iid}")
        h = slot_item.get("itemHash")
        if h and h not in seen_hashes:
            seen_hashes.add(h)
            hash_parts.append(f"hash:{h}")
    if exotic and exotic.get("hash") and exotic["hash"] not in seen_hashes:
        hash_parts.append(f"hash:{exotic['hash']}")
    # Prefer exact instance ids when we have inventory rolls.
    search_parts = id_parts or hash_parts
    if not search_parts:
        return None
    search = " or ".join(search_parts)
    url = "https://app.destinyitemmanager.com/inventory?search=" + quote(search)
    return {"search": search, "url": url}


def _resolve_stat_priority(
    requested: Optional[list[str]], archetype: Optional[dict]
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in requested or []:
        key = _normalize_stat_name(raw)
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    if not ordered:
        for raw in (archetype or {}).get("stat_priority") or []:
            key = _normalize_stat_name(raw)
            if key and key not in seen:
                seen.add(key)
                ordered.append(key)
    if not ordered:
        ordered = ["weapons", "health", "class"]
    return ordered


def generate_build(
    query: str,
    profile: dict,
    *,
    class_type: Optional[str] = None,
    character_id: Optional[str] = None,
    stat_priority: Optional[list[str]] = None,
    include_vault: bool = True,
) -> dict:
    characters = profile.get("characters") or []
    items, character_class = _filter_items_for_character(
        profile.get("items") or [],
        characters,
        character_id,
        include_vault=include_vault,
    )

    exotic = resolve_exotic(query)
    exotic_name = exotic["name"] if exotic else None
    archetype = arch.find_archetype(exotic_name) if exotic_name else None
    resolved_class = _resolve_class(
        query, exotic, archetype, class_type, character_class
    )
    resolved_stats = _resolve_stat_priority(stat_priority, archetype)
    stat_labels = [ARMOR_STAT_LABELS[k] for k in resolved_stats]

    anchor = [exotic["hash"]] if exotic else []

    kb_weapons = _kb_section(anchor, "weapon")
    kb_mods = _kb_section(anchor, "mod")
    kb_fragments = _kb_section(anchor, "fragment")
    kb_aspects = _kb_section(anchor, "aspect")
    kb_subclass = _kb_section(anchor, "subclass")
    kb_sources = ref_store.references_mentioning(anchor)

    recommended_weapon_hashes = {f["manifest_hash"] for f in kb_weapons}

    weapons = _pick_weapons(items, exotic, recommended_weapon_hashes)
    armor = _pick_armor(items, exotic, resolved_class, resolved_stats)

    owned = _owned_hashes(items)
    # Ownership of the exotic should consider the full profile, not just filtered items.
    all_owned = _owned_hashes(profile.get("items") or [])
    exotic_owned = bool(exotic and exotic["hash"] in all_owned)

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

    rationale = _build_rationale(
        query,
        exotic,
        exotic_owned,
        archetype,
        kb_sources,
        resolved_class,
        character_id,
        character_class,
    )

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
        "classType": CLASS_NAMES.get(resolved_class) if resolved_class is not None else "any",
        "characterId": character_id,
        "subclass": subclass,
        "weapons": weapons,
        "armor": armor,
        "aspects": merge_named(kb_aspects, (archetype or {}).get("aspects")),
        "fragments": merge_named(kb_fragments, (archetype or {}).get("fragments")),
        "mods": merge_named(kb_mods, (archetype or {}).get("mods")),
        "statPriority": stat_labels,
        "availableStats": [ARMOR_STAT_LABELS[k] for k in ARMOR_STAT_ORDER],
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
    class_type: Optional[int],
    character_id: Optional[str],
    character_class: Optional[str],
) -> str:
    if not exotic:
        return (
            "Could not confidently match an exotic to your query. Try naming the exotic "
            "directly, e.g. 'Telesto build'."
        )
    parts = [f"Built around {exotic['name']} ({exotic['entity_type']})."]
    parts.append("You own this exotic." if exotic_owned else "You do NOT own this exotic yet.")
    if class_type is not None:
        parts.append(f"Armor locked to {CLASS_NAMES[class_type].title()}.")
    else:
        parts.append(
            "No class selected — armor was skipped. Pick a character or class so pieces don't mix."
        )
    if character_id:
        label = (character_class or "character").title()
        parts.append(f"Searching {label} inventory + vault.")
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
