"""D2ArmorPicker-style armor set search against target stats."""

from __future__ import annotations

from itertools import product
from typing import Any, Optional
from urllib.parse import quote  # noqa: F401 — used by solve_armor

from ..bungie import manifest
from .engine import (
    ARMOR_SLOTS,
    ARMOR_STAT_HASHES,
    ARMOR_STAT_LABELS,
    ARMOR_STAT_ORDER,
    CLASS_IDS,
    CLASS_NAMES,
    _armor_stat_value,
    _filter_items_for_character,
)

ELEMENTS = ["arc", "solar", "void", "stasis", "strand", "prism"]

# Fragments whose investmentStats don't map cleanly to a single armor stat.
# Echo of Persistence: -10 class ability regen → treat as -10 Class for the chosen class.
FRAGMENT_OVERRIDES: dict[int, dict[str, int]] = {
    # Echo of Persistence — investmentStats triples -10 across Weapons/Health/Class;
    # in-game it's a single Class ability regen penalty (D2ArmorPicker convention).
    2272984671: {"class": -10},
}


def _bungie_icon(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path if path.startswith("http") else "https://www.bungie.net" + path


def _stat_vector(item: dict) -> dict[str, int]:
    return {k: _armor_stat_value(item, k) for k in ARMOR_STAT_ORDER}


def _empty_stats() -> dict[str, int]:
    return {k: 0 for k in ARMOR_STAT_ORDER}


def _add_stats(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {k: a.get(k, 0) + b.get(k, 0) for k in ARMOR_STAT_ORDER}


def _plug_element(plug_cat: str) -> Optional[str]:
    cat = (plug_cat or "").lower()
    for el in ELEMENTS:
        if el in cat:
            return el
    # Stasis fragments often use shared.fragments without stasis in the path.
    if "shared.fragments" in cat and "prism" not in cat:
        return "stasis"
    return None


def _investment_armor_bonus(definition: dict) -> dict[str, int]:
    bonus = _empty_stats()
    inv_to_key = {h: k for k, h in ARMOR_STAT_HASHES.items()}
    for entry in definition.get("investmentStats") or []:
        key = inv_to_key.get(entry.get("statTypeHash"))
        if key:
            bonus[key] += int(entry.get("value") or 0)
    return bonus


def fragment_bonus(fragment_hashes: list[int]) -> dict[str, int]:
    total = _empty_stats()
    for h in fragment_hashes:
        if h in FRAGMENT_OVERRIDES:
            total = _add_stats(total, {**_empty_stats(), **FRAGMENT_OVERRIDES[h]})
            continue
        d = manifest.get_item(int(h))
        if not d:
            continue
        total = _add_stats(total, _investment_armor_bonus(d))
    return total


def list_exotic_armor(
    class_type: str,
    owned_hashes: Optional[set[int]] = None,
) -> list[dict]:
    """Exotic armor for a class, deduped by name, owned first."""
    cid = CLASS_IDS.get(class_type.lower())
    if cid is None:
        return []
    owned_hashes = owned_hashes or set()
    rows = [
        r
        for r in manifest.exotic_names()
        if r.get("entity_type") == "armor" and r.get("class_type") == cid
    ]
    # Prefer a hash the user owns when multiple ornament/definition hashes share a name.
    by_name: dict[str, dict] = {}
    for r in rows:
        name = r["name"]
        h = int(r["hash"])
        prev = by_name.get(name)
        if prev is None:
            by_name[name] = r
            continue
        prev_owned = int(prev["hash"]) in owned_hashes
        cur_owned = h in owned_hashes
        if cur_owned and not prev_owned:
            by_name[name] = r

    out = []
    for name, r in by_name.items():
        h = int(r["hash"])
        d = manifest.get_item(h)
        dp = (d or {}).get("displayProperties") or {}
        inv = (d or {}).get("inventory") or {}
        bucket = inv.get("bucketTypeHash")
        from ..bungie.profile import ARMOR_BUCKETS

        slot = ARMOR_BUCKETS.get(bucket)
        out.append(
            {
                "hash": h,
                "name": name,
                "icon": _bungie_icon(dp.get("icon")),
                "classType": class_type.lower(),
                "slot": slot,
                "owned": h in owned_hashes,
            }
        )
    out.sort(key=lambda x: (not x["owned"], x["name"].lower()))
    return out


def list_subclass_options(class_type: str, element: Optional[str] = None) -> dict:
    """Aspects + fragments for a class/element with armor-stat bonuses."""
    class_type = class_type.lower()
    element = (element or "").lower() or None
    aspects: list[dict] = []
    fragments: list[dict] = []

    for r in manifest.all_names(["aspect", "fragment"]):
        h = int(r["hash"])
        d = manifest.get_item(h)
        if not d:
            continue
        plug_cat = ((d.get("plug") or {}).get("plugCategoryIdentifier") or "").lower()
        el = _plug_element(plug_cat)
        # Aspects are class-scoped (warlock.solar.aspects); fragments are mostly shared.
        if r["entity_type"] == "aspect":
            if class_type not in plug_cat:
                continue
            if element and el and el != element:
                continue
            if element and not el:
                continue
            dp = d.get("displayProperties") or {}
            aspects.append(
                {
                    "hash": h,
                    "name": r["name"],
                    "icon": _bungie_icon(dp.get("icon")),
                    "element": el,
                    "type": "aspect",
                    "bonus": _investment_armor_bonus(d),
                }
            )
        else:
            if element and el and el != element:
                continue
            if element and not el:
                continue
            dp = d.get("displayProperties") or {}
            bonus = (
                {**_empty_stats(), **FRAGMENT_OVERRIDES[h]}
                if h in FRAGMENT_OVERRIDES
                else _investment_armor_bonus(d)
            )
            fragments.append(
                {
                    "hash": h,
                    "name": r["name"],
                    "icon": _bungie_icon(dp.get("icon")),
                    "element": el,
                    "type": "fragment",
                    "bonus": bonus,
                    "hasStatBonus": any(bonus.values()),
                }
            )

    aspects.sort(key=lambda x: x["name"].lower())
    # Stat-affecting fragments first.
    fragments.sort(key=lambda x: (not x["hasStatBonus"], x["name"].lower()))
    return {
        "elements": ELEMENTS,
        "aspects": aspects,
        "fragments": fragments,
    }


def _piece_score(vec: dict[str, int], targets: dict[str, int], bonus: dict[str, int]) -> float:
    """How useful is this piece toward unmet targets (ignoring overshoot a bit)."""
    score = 0.0
    for k in ARMOR_STAT_ORDER:
        need = max(0, targets.get(k, 0) - bonus.get(k, 0))
        if need <= 0:
            continue
        score += min(vec.get(k, 0), need) * (1.0 + need / 100.0)
    score += sum(vec.values()) * 0.01
    return score


def _dominated(a: dict[str, int], b: dict[str, int]) -> bool:
    """True if a is strictly worse or equal on every stat vs b (and worse on one)."""
    le = all(a.get(k, 0) <= b.get(k, 0) for k in ARMOR_STAT_ORDER)
    lt = any(a.get(k, 0) < b.get(k, 0) for k in ARMOR_STAT_ORDER)
    return le and lt


def _prune_slot(
    pieces: list[dict], targets: dict[str, int], bonus: dict[str, int], keep: int
) -> list[dict]:
    scored = []
    for p in pieces:
        vec = _stat_vector(p)
        scored.append((p, vec, _piece_score(vec, targets, bonus)))
    scored.sort(key=lambda t: t[2], reverse=True)

    kept: list[tuple[dict, dict[str, int]]] = []
    for p, vec, _s in scored:
        if any(_dominated(vec, other_vec) for _op, other_vec in kept):
            continue
        # Also drop if equal on all stats to an already-kept piece (keep higher power).
        dup = False
        for i, (op, ov) in enumerate(kept):
            if all(vec.get(k, 0) == ov.get(k, 0) for k in ARMOR_STAT_ORDER):
                if (p.get("power") or 0) > (op.get("power") or 0):
                    kept[i] = (p, vec)
                dup = True
                break
        if dup:
            continue
        kept.append((p, vec))
        if len(kept) >= keep:
            break
    return [p for p, _v in kept]


def _set_score(
    totals: dict[str, int], targets: dict[str, int]
) -> tuple[float, dict[str, int], dict[str, int]]:
    under = {k: max(0, targets.get(k, 0) - totals.get(k, 0)) for k in ARMOR_STAT_ORDER}
    over = {k: max(0, totals.get(k, 0) - targets.get(k, 0)) for k in ARMOR_STAT_ORDER}
    # Primary: hit targets. Secondary: avoid huge waste.
    score = sum(under.values()) * 1000 + sum(over.values())
    return float(score), under, over


def _serialize_piece(item: dict) -> dict:
    stats = _stat_vector(item)
    return {
        "itemHash": item.get("itemHash"),
        "itemInstanceId": item.get("itemInstanceId"),
        "name": item.get("name"),
        "icon": item.get("icon"),
        "slot": item.get("slot"),
        "tier": item.get("tier"),
        "isExotic": item.get("isExotic"),
        "power": item.get("power"),
        "location": item.get("location"),
        "characterId": item.get("characterId"),
        "classType": item.get("classType"),
        "stats": {ARMOR_STAT_LABELS[k]: stats[k] for k in ARMOR_STAT_ORDER},
        "statKeys": stats,
    }


def _normalize_targets(targets: Optional[dict[str, int]]) -> dict[str, int]:
    norm = _empty_stats()
    targets = targets or {}
    for k in ARMOR_STAT_ORDER:
        raw = targets.get(k)
        if raw is None:
            raw = targets.get(ARMOR_STAT_LABELS[k])
        try:
            v = int(raw or 0)
        except (TypeError, ValueError):
            v = 0
        norm[k] = max(0, min(200, v))
    return norm


def _prepare_armor_pool(
    profile: dict,
    *,
    class_type: str,
    exotic_hash: Optional[int],
    character_id: Optional[str],
    include_vault: bool,
    fragment_hashes: Optional[list[int]],
    targets_for_exotic_pick: Optional[dict[str, int]] = None,
) -> tuple[Optional[dict[str, list[dict]]], dict[str, int], Optional[str]]:
    """Build per-slot armor lists. Returns (by_slot, fragment_bonus, error)."""
    class_type = class_type.lower()
    characters = profile.get("characters") or []
    items, _ = _filter_items_for_character(
        profile.get("items") or [],
        characters,
        character_id,
        include_vault=include_vault,
    )
    armor = [
        i
        for i in items
        if i.get("kind") == "armor"
        and i.get("slot") in ARMOR_SLOTS
        and i.get("classType") == class_type
    ]
    bonus = fragment_bonus([int(h) for h in (fragment_hashes or [])])
    by_slot: dict[str, list[dict]] = {s: [] for s in ARMOR_SLOTS}
    for a in armor:
        by_slot[a["slot"]].append(a)

    pick_targets = targets_for_exotic_pick or _empty_stats()
    if exotic_hash:
        exotic_hash = int(exotic_hash)
        owned = [a for a in armor if a.get("itemHash") == exotic_hash]
        if not owned:
            d = manifest.get_item(exotic_hash)
            name = ((d or {}).get("displayProperties") or {}).get("name") or exotic_hash
            return None, bonus, f"Exotic not found in this character/vault pool: {name}"
        owned.sort(
            key=lambda a: (
                _piece_score(_stat_vector(a), pick_targets, bonus),
                a.get("power") or 0,
            ),
            reverse=True,
        )
        exotic_piece = owned[0]
        exotic_slot = exotic_piece["slot"]
        by_slot[exotic_slot] = [exotic_piece]
        for s in ARMOR_SLOTS:
            if s == exotic_slot:
                continue
            by_slot[s] = [a for a in by_slot[s] if not a.get("isExotic")]
    else:
        for s in ARMOR_SLOTS:
            by_slot[s] = [a for a in by_slot[s] if not a.get("isExotic")] or by_slot[s]

    if any(not by_slot[s] for s in ARMOR_SLOTS):
        missing = [s for s in ARMOR_SLOTS if not by_slot[s]]
        return None, bonus, f"No armor available for slot(s): {', '.join(missing)}"
    return by_slot, bonus, None


def _absolute_maxes(by_slot: dict[str, list[dict]], bonus: dict[str, int]) -> dict[str, int]:
    """Best possible total per stat if that stat is stacked alone."""
    out = _empty_stats()
    for stat in ARMOR_STAT_ORDER:
        total = bonus.get(stat, 0)
        for slot in ARMOR_SLOTS:
            best = 0
            for p in by_slot[slot]:
                best = max(best, _stat_vector(p).get(stat, 0))
            total += best
        out[stat] = min(200, total)
    return out


def _prune_for_caps(by_slot: dict[str, list[dict]], keep_per_stat: int = 3, max_per_slot: int = 6) -> dict[str, list[dict]]:
    """Keep a small set of top pieces per slot so cap search stays interactive."""
    pruned: dict[str, list[dict]] = {}
    for slot in ARMOR_SLOTS:
        scored: dict[Any, tuple[float, dict]] = {}
        for stat in ARMOR_STAT_ORDER:
            ranked = sorted(
                by_slot[slot],
                key=lambda p: (_stat_vector(p).get(stat, 0), p.get("power") or 0),
                reverse=True,
            )[:keep_per_stat]
            for i, p in enumerate(ranked):
                key = p.get("itemInstanceId") or p.get("itemHash")
                # Prefer pieces that rank highly on any single stat.
                score = (keep_per_stat - i) + (_stat_vector(p).get(stat, 0) / 100.0)
                prev = scored.get(key)
                if prev is None or score > prev[0]:
                    scored[key] = (score, p)
        # Hard cap pieces per slot — 6^5 = 7776 combos, fine for 6 focus passes.
        top = sorted(scored.values(), key=lambda t: t[0], reverse=True)[:max_per_slot]
        pruned[slot] = [p for _s, p in top] or list(by_slot[slot])[:1]
    return pruned


def _max_stat_under_mins(
    slot_data: dict[str, list[tuple[dict, dict[str, int]]]],
    bonus: dict[str, int],
    focus: str,
    mins: dict[str, int],
) -> int:
    """Max reachable `focus` among sets that meet all `mins`."""
    best = -1
    slots = ARMOR_SLOTS
    lists = [slot_data[s] for s in slots]
    # Order pieces in each slot by focus desc to find good values early.
    lists = [
        sorted(lst, key=lambda t: t[1].get(focus, 0), reverse=True) for lst in lists
    ]
    for combo in product(*lists):
        totals = dict(bonus)
        for _piece, vec in combo:
            for k in ARMOR_STAT_ORDER:
                totals[k] += vec[k]
        if any(totals[k] < mins.get(k, 0) for k in ARMOR_STAT_ORDER):
            continue
        if totals[focus] > best:
            best = totals[focus]
            if best >= 200:
                return 200
    return best


def compute_stat_caps(
    profile: dict,
    *,
    class_type: str,
    targets: Optional[dict[str, int]] = None,
    exotic_hash: Optional[int] = None,
    character_id: Optional[str] = None,
    include_vault: bool = True,
    fragment_hashes: Optional[list[int]] = None,
) -> dict[str, Any]:
    """D2ArmorPicker-style caps: max per stat given inventory + other targets as mins."""
    class_type = class_type.lower()
    if class_type not in CLASS_IDS:
        raise ValueError("classType must be titan, hunter, or warlock")

    norm_targets = _normalize_targets(targets)
    by_slot, bonus, err = _prepare_armor_pool(
        profile,
        class_type=class_type,
        exotic_hash=exotic_hash,
        character_id=character_id,
        include_vault=include_vault,
        fragment_hashes=fragment_hashes,
        targets_for_exotic_pick=norm_targets,
    )
    if err or not by_slot:
        return {
            "ok": False,
            "error": err or "No armor pool",
            "absoluteMax": {ARMOR_STAT_LABELS[k]: 0 for k in ARMOR_STAT_ORDER},
            "max": {ARMOR_STAT_LABELS[k]: 0 for k in ARMOR_STAT_ORDER},
            "fragmentBonus": {ARMOR_STAT_LABELS[k]: bonus[k] for k in ARMOR_STAT_ORDER},
        }

    absolute = _absolute_maxes(by_slot, bonus)

    # No mins set → absolute inventory max for every slider (fast path).
    if all(v <= 0 for v in norm_targets.values()):
        return {
            "ok": True,
            "error": None,
            "classType": class_type,
            "absoluteMax": {ARMOR_STAT_LABELS[k]: absolute[k] for k in ARMOR_STAT_ORDER},
            "max": {ARMOR_STAT_LABELS[k]: absolute[k] for k in ARMOR_STAT_ORDER},
            "fragmentBonus": {ARMOR_STAT_LABELS[k]: bonus[k] for k in ARMOR_STAT_ORDER},
            "targets": {ARMOR_STAT_LABELS[k]: norm_targets[k] for k in ARMOR_STAT_ORDER},
        }

    pruned = _prune_for_caps(by_slot)
    slot_data = {s: [(p, _stat_vector(p)) for p in pruned[s]] for s in ARMOR_SLOTS}

    constrained = _empty_stats()
    for focus in ARMOR_STAT_ORDER:
        # Treat OTHER targets as minimums; leave focus free so we can find its ceiling.
        mins = {k: (norm_targets[k] if k != focus else 0) for k in ARMOR_STAT_ORDER}
        # If this focus itself is the only non-zero target, its cap is absolute.
        others = [k for k in ARMOR_STAT_ORDER if k != focus and norm_targets[k] > 0]
        if not others:
            constrained[focus] = absolute[focus]
            continue
        best_val = _max_stat_under_mins(slot_data, bonus, focus, mins)
        if best_val < 0:
            # Other mins infeasible together — don't claim more than absolute.
            constrained[focus] = 0
        else:
            constrained[focus] = min(200, best_val, absolute[focus])

    return {
        "ok": True,
        "error": None,
        "classType": class_type,
        "absoluteMax": {ARMOR_STAT_LABELS[k]: absolute[k] for k in ARMOR_STAT_ORDER},
        "max": {ARMOR_STAT_LABELS[k]: constrained[k] for k in ARMOR_STAT_ORDER},
        "fragmentBonus": {ARMOR_STAT_LABELS[k]: bonus[k] for k in ARMOR_STAT_ORDER},
        "targets": {ARMOR_STAT_LABELS[k]: norm_targets[k] for k in ARMOR_STAT_ORDER},
    }


def solve_armor(
    profile: dict,
    *,
    class_type: str,
    targets: dict[str, int],
    exotic_hash: Optional[int] = None,
    character_id: Optional[str] = None,
    include_vault: bool = True,
    fragment_hashes: Optional[list[int]] = None,
    aspect_hashes: Optional[list[int]] = None,
    max_results: int = 12,
    per_slot: int = 14,
) -> dict[str, Any]:
    class_type = class_type.lower()
    if class_type not in CLASS_IDS:
        raise ValueError("classType must be titan, hunter, or warlock")

    norm_targets = _normalize_targets(targets)
    frag_hashes = [int(h) for h in (fragment_hashes or [])]
    asp_hashes = [int(h) for h in (aspect_hashes or [])]

    by_slot, bonus, err = _prepare_armor_pool(
        profile,
        class_type=class_type,
        exotic_hash=exotic_hash,
        character_id=character_id,
        include_vault=include_vault,
        fragment_hashes=frag_hashes,
        targets_for_exotic_pick=norm_targets,
    )
    if err or not by_slot:
        return {
            "ok": False,
            "error": err or "No armor pool",
            "results": [],
            "fragmentBonus": {ARMOR_STAT_LABELS[k]: bonus[k] for k in ARMOR_STAT_ORDER},
            "targets": {ARMOR_STAT_LABELS[k]: norm_targets[k] for k in ARMOR_STAT_ORDER},
        }

    exotic_slot = None
    if exotic_hash:
        # Pool already pinned the exotic slot to a single piece.
        for s in ARMOR_SLOTS:
            if by_slot[s] and by_slot[s][0].get("itemHash") == int(exotic_hash):
                exotic_slot = s
                break

    pruned = {
        s: _prune_slot(by_slot[s], norm_targets, bonus, per_slot if s != exotic_slot else 1)
        for s in ARMOR_SLOTS
    }
    missing_slots = [s for s in ARMOR_SLOTS if not pruned[s]]
    if missing_slots:
        return {
            "ok": False,
            "error": f"No armor available for slot(s): {', '.join(missing_slots)}",
            "results": [],
            "fragmentBonus": {ARMOR_STAT_LABELS[k]: bonus[k] for k in ARMOR_STAT_ORDER},
            "targets": {ARMOR_STAT_LABELS[k]: norm_targets[k] for k in ARMOR_STAT_ORDER},
        }

    # Precompute vectors.
    slot_data = {
        s: [(p, _stat_vector(p)) for p in pruned[s]] for s in ARMOR_SLOTS
    }

    best: list[tuple[float, dict]] = []
    for combo in product(*(slot_data[s] for s in ARMOR_SLOTS)):
        totals = dict(bonus)
        pieces = {}
        for slot, (piece, vec) in zip(ARMOR_SLOTS, combo):
            pieces[slot] = piece
            for k in ARMOR_STAT_ORDER:
                totals[k] += vec[k]
        score, under, over = _set_score(totals, norm_targets)
        entry = {
            "score": score,
            "tiersMet": sum(1 for k in ARMOR_STAT_ORDER if under[k] == 0),
            "totals": {ARMOR_STAT_LABELS[k]: totals[k] for k in ARMOR_STAT_ORDER},
            "under": {ARMOR_STAT_LABELS[k]: under[k] for k in ARMOR_STAT_ORDER},
            "over": {ARMOR_STAT_LABELS[k]: over[k] for k in ARMOR_STAT_ORDER},
            "armor": {s: _serialize_piece(pieces[s]) for s in ARMOR_SLOTS},
        }
        if len(best) < max_results:
            best.append((score, entry))
            best.sort(key=lambda t: t[0])
        elif score < best[-1][0]:
            best[-1] = (score, entry)
            best.sort(key=lambda t: t[0])

    results = []
    for score, entry in best:
        # Prefer instance ids so DIM highlights the exact rolls.
        id_parts = []
        hash_parts = []
        for s in ARMOR_SLOTS:
            piece = entry["armor"][s]
            iid = piece.get("itemInstanceId")
            if iid:
                id_parts.append(f"id:{iid}")
            elif piece.get("itemHash"):
                hash_parts.append(f"hash:{piece['itemHash']}")
        search = " or ".join(id_parts or list(dict.fromkeys(hash_parts)))
        entry["dim"] = {
            "search": search,
            "url": "https://app.destinyitemmanager.com/inventory?search=" + quote(search),
        }
        results.append(entry)

    # Selected plug summaries for the UI.
    selected_plugs = []
    for h in asp_hashes + frag_hashes:
        d = manifest.get_item(h)
        if not d:
            continue
        dp = d.get("displayProperties") or {}
        b = (
            {**_empty_stats(), **FRAGMENT_OVERRIDES[h]}
            if h in FRAGMENT_OVERRIDES
            else _investment_armor_bonus(d)
        )
        selected_plugs.append(
            {
                "hash": h,
                "name": dp.get("name"),
                "icon": _bungie_icon(dp.get("icon")),
                "bonus": {ARMOR_STAT_LABELS[k]: b[k] for k in ARMOR_STAT_ORDER},
            }
        )

    return {
        "ok": True,
        "error": None,
        "classType": class_type,
        "characterId": character_id,
        "exoticHash": exotic_hash,
        "targets": {ARMOR_STAT_LABELS[k]: norm_targets[k] for k in ARMOR_STAT_ORDER},
        "fragmentBonus": {ARMOR_STAT_LABELS[k]: bonus[k] for k in ARMOR_STAT_ORDER},
        "effectiveTargets": {
            ARMOR_STAT_LABELS[k]: max(0, norm_targets[k] - bonus[k]) for k in ARMOR_STAT_ORDER
        },
        "selectedPlugs": selected_plugs,
        "searchedCombos": (
            len(slot_data["helmet"])
            * len(slot_data["gauntlets"])
            * len(slot_data["chest"])
            * len(slot_data["legs"])
            * len(slot_data["class"])
        ),
        "results": results,
    }


def owned_exotic_hashes(profile: dict, class_type: str) -> set[int]:
    return {
        int(i["itemHash"])
        for i in profile.get("items") or []
        if i.get("kind") == "armor"
        and i.get("isExotic")
        and i.get("classType") == class_type.lower()
    }
