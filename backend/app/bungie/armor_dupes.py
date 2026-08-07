"""Find legendary Armor 3.0 pieces that share the same base stat distribution."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from . import manifest, profile as profile_svc

# Weapons, Health, Class, Grenade, Super, Melee
STAT_ORDER = [
    2996146975,
    392767087,
    1943323491,
    1735777505,
    144602215,
    4244567218,
]
STAT_LABELS = ["Weapons", "Health", "Class", "Grenade", "Super", "Melee"]

ARMOR_BUCKETS = {
    3448274439: "helmet",
    3551918588: "gauntlets",
    14239492: "chest",
    20886954: "legs",
    1585787867: "class",
}
CLASS_TYPES = {0: "titan", 1: "hunter", 2: "warlock", 3: "unknown"}


def _bungie_icon(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return "https://www.bungie.net" + path


def _plug_summary(plug_hash: int) -> Optional[dict]:
    d = manifest.get_item(plug_hash)
    if not d:
        return None
    dp = d.get("displayProperties") or {}
    plug = d.get("plug") or {}
    inv = d.get("investmentStats") or []
    return {
        "hash": plug_hash,
        "name": dp.get("name") or None,
        "icon": _bungie_icon(dp.get("icon")),
        "category": plug.get("plugCategoryIdentifier") or "",
        "investment": [
            {"statHash": i.get("statTypeHash"), "value": int(i.get("value") or 0)}
            for i in inv
            if i.get("statTypeHash") is not None
        ],
    }


def _add_investment(totals: dict[int, int], plug: Optional[dict]) -> None:
    if not plug:
        return
    for inv in plug.get("investment") or []:
        h = inv.get("statHash")
        if h in totals:
            totals[h] += int(inv.get("value") or 0)


def _live_vector(stats_block: Optional[dict]) -> list[int]:
    raw = (stats_block or {}).get("stats") or {}
    out: list[int] = []
    for h in STAT_ORDER:
        cell = raw.get(str(h)) or raw.get(h) or {}
        out.append(int(cell.get("value") or 0))
    return out


def _labeled(values: list[int]) -> dict[str, int]:
    return {STAT_LABELS[i]: values[i] for i in range(len(STAT_ORDER))}


def _walk_armor_instances(resp: dict) -> list[tuple[dict, str, Optional[str]]]:
    """Yield (raw_item, location, characterId) for armor instances.

    Assumes DestinyInventoryItemDefinition hashes are already warm in the
    manifest cache (call get_definitions first for best performance).
    """
    out: list[tuple[dict, str, Optional[str]]] = []

    def consider(items: Optional[list], location: str, character_id: Optional[str]) -> None:
        for it in items or []:
            h = it.get("itemHash")
            if not it.get("itemInstanceId") or not h:
                continue
            d = manifest.get_item(int(h))
            if not d or d.get("itemType") != 2:
                continue
            out.append((it, location, character_id))

    consider(
        ((resp.get("profileInventory") or {}).get("data") or {}).get("items"),
        "vault",
        None,
    )
    for cid, inv in ((resp.get("characterInventories") or {}).get("data") or {}).items():
        consider(inv.get("items"), "character", cid)
    for cid, inv in ((resp.get("characterEquipment") or {}).get("data") or {}).items():
        consider(inv.get("items"), "equipped", cid)
    return out


def _all_instance_item_hashes(resp: dict) -> set[int]:
    hashes: set[int] = set()

    def take(items: Optional[list]) -> None:
        for it in items or []:
            h = it.get("itemHash")
            if h is not None:
                try:
                    hashes.add(int(h))
                except (TypeError, ValueError):
                    pass
            o = it.get("overrideStyleItemHash")
            if o is not None:
                try:
                    hashes.add(int(o))
                except (TypeError, ValueError):
                    pass

    take(((resp.get("profileInventory") or {}).get("data") or {}).get("items"))
    for inv in ((resp.get("characterInventories") or {}).get("data") or {}).values():
        take(inv.get("items"))
    for inv in ((resp.get("characterEquipment") or {}).get("data") or {}).values():
        take(inv.get("items"))
    return hashes


def _classify_sockets(socket_block: Optional[dict]) -> dict[str, Any]:
    archetype: Optional[dict] = None
    tuning: Optional[dict] = None
    artifice: Optional[dict] = None
    armor_stats: list[dict] = []

    for sock in (socket_block or {}).get("sockets") or []:
        ph = sock.get("plugHash")
        if not ph:
            continue
        summary = _plug_summary(int(ph))
        if not summary:
            continue
        cat = (summary.get("category") or "").lower()
        name = (summary.get("name") or "").lower()
        if cat == "armor_archetypes":
            archetype = summary
        elif cat == "armor_stats":
            armor_stats.append(summary)
        elif "tuning.mods" in cat:
            tuning = summary
        elif cat.startswith("enhancements.artifice"):
            if "empty" in name or "locked" in name:
                continue
            artifice = summary

    return {
        "archetype": archetype,
        "tuning": tuning,
        "artifice": artifice,
        "armorStats": armor_stats,
    }


def find_armor_dupes(resp: dict) -> dict:
    """
    Group Armor 3.0 legendaries that share class + slot + base roll.

    Base roll = sum of investmentStats from armor_archetypes + armor_stats plugs
    (mods / masterwork / tuning are ignored so identical distributions match).
    """
    sockets = ((resp.get("itemComponents") or {}).get("sockets") or {}).get("data") or {}
    stats = ((resp.get("itemComponents") or {}).get("stats") or {}).get("data") or {}
    instances = ((resp.get("itemComponents") or {}).get("instances") or {}).get("data") or {}

    # Warm ALL inventory item defs first (walk filters armor via cached get_item).
    item_hashes = _all_instance_item_hashes(resp)
    plug_hashes: set[int] = set()
    for block in sockets.values():
        for sock in (block or {}).get("sockets") or []:
            ph = sock.get("plugHash")
            if ph:
                try:
                    plug_hashes.add(int(ph))
                except (TypeError, ValueError):
                    pass
    if item_hashes or plug_hashes:
        manifest.get_definitions(
            "DestinyInventoryItemDefinition", list(item_hashes | plug_hashes)
        )

    pieces: list[dict] = []
    for raw, location, character_id in _walk_armor_instances(resp):
        item_hash = int(raw["itemHash"])
        instance_id = raw["itemInstanceId"]
        definition = manifest.get_item(item_hash) or {}
        inv = definition.get("inventory") or {}
        tier = inv.get("tierType", 0)
        dp = definition.get("displayProperties") or {}
        bucket = inv.get("bucketTypeHash")
        slot = ARMOR_BUCKETS.get(bucket)
        if not slot:
            continue
        class_type = CLASS_TYPES.get(definition.get("classType", 3), "unknown")

        plugs = _classify_sockets(sockets.get(instance_id))
        # Armor 3.0 only — older armor lacks archetype / armor_stats plugs.
        if not plugs["archetype"] and not plugs["armorStats"]:
            continue

        base_totals = {h: 0 for h in STAT_ORDER}
        _add_investment(base_totals, plugs["archetype"])
        for p in plugs["armorStats"]:
            _add_investment(base_totals, p)
        base_vec = [base_totals[h] for h in STAT_ORDER]
        if not any(base_vec):
            continue

        live_vec = _live_vector(stats.get(instance_id))
        power = None
        inst = instances.get(instance_id)
        if inst:
            power = (inst.get("primaryStat") or {}).get("value")

        # Prefer ornament/style icon when present.
        icon = _bungie_icon(dp.get("icon"))
        override = raw.get("overrideStyleItemHash")
        if override:
            odef = manifest.get_item(int(override))
            if odef:
                oicon = (odef.get("displayProperties") or {}).get("icon")
                if oicon:
                    icon = _bungie_icon(oicon)

        pieces.append(
            {
                "itemHash": item_hash,
                "itemInstanceId": instance_id,
                "name": dp.get("name") or "Unknown",
                "icon": icon,
                "slot": slot,
                "classType": class_type,
                "tier": "exotic" if tier == 6 else "legendary",
                "isExotic": tier == 6,
                "location": location,
                "characterId": character_id,
                "power": power,
                "isMasterwork": bool((raw.get("state") or 0) & 4),
                "rollStats": _labeled(base_vec),
                "rollVector": base_vec,
                "liveStats": _labeled(live_vec),
                "archetype": {
                    "hash": plugs["archetype"]["hash"],
                    "name": plugs["archetype"].get("name"),
                    "icon": plugs["archetype"].get("icon"),
                }
                if plugs["archetype"]
                else None,
                "tuning": {
                    "hash": plugs["tuning"]["hash"],
                    "name": plugs["tuning"].get("name") or "Empty Tuning Mod Socket",
                    "icon": plugs["tuning"].get("icon"),
                    "isEmpty": "empty" in ((plugs["tuning"].get("name") or "").lower()),
                }
                if plugs["tuning"]
                else None,
                "artifice": {
                    "hash": plugs["artifice"]["hash"],
                    "name": plugs["artifice"].get("name"),
                    "icon": plugs["artifice"].get("icon"),
                }
                if plugs["artifice"]
                else None,
            }
        )

    groups_map: dict[tuple, list[dict]] = defaultdict(list)
    for p in pieces:
        key = (p["classType"], p["slot"], tuple(p["rollVector"]))
        # Exotics only dupe against the same exotic hash.
        if p["isExotic"]:
            key = (p["classType"], p["slot"], p["itemHash"], tuple(p["rollVector"]))
        groups_map[key].append(p)

    groups: list[dict] = []
    for key, members in groups_map.items():
        if len(members) < 2:
            continue
        # Prefer showing pieces with different tuning first (that's the decision).
        members_sorted = sorted(
            members,
            key=lambda m: (
                0 if (m.get("tuning") and not m["tuning"].get("isEmpty")) else 1,
                -(m.get("power") or 0),
                m.get("name") or "",
            ),
        )
        tuning_names = {
            (m.get("tuning") or {}).get("name") or "None" for m in members_sorted
        }
        groups.append(
            {
                "classType": members_sorted[0]["classType"],
                "slot": members_sorted[0]["slot"],
                "rollStats": members_sorted[0]["rollStats"],
                "archetype": members_sorted[0].get("archetype"),
                "count": len(members_sorted),
                "tuningDiffers": len(tuning_names) > 1,
                "pieces": members_sorted,
            }
        )

    groups.sort(key=lambda g: (-g["count"], g["classType"], g["slot"]))
    return {
        "ok": True,
        "scanned": len(pieces),
        "groupCount": len(groups),
        "groups": groups,
        "statOrder": STAT_LABELS,
    }


async def scan_armor_dupes() -> dict:
    # Reuse the shared profile cache when warm (avoid a second GetProfile).
    _membership, resp = await profile_svc.get_profile_raw_cached()
    # Socket/manifest classification is CPU + SQLite heavy — keep the event loop free.
    import asyncio

    return await asyncio.to_thread(find_armor_dupes, resp)


def find_weapon_dupes(items: list[dict]) -> dict:
    """Group duplicate weapon copies (same itemHash) for vault cleanup."""
    weapons = [
        i
        for i in items
        if i.get("kind") == "weapon" and i.get("itemInstanceId") and i.get("itemHash")
    ]
    by_hash: dict[int, list[dict]] = defaultdict(list)
    for w in weapons:
        by_hash[int(w["itemHash"])].append(w)

    groups: list[dict] = []
    for item_hash, members in by_hash.items():
        if len(members) < 2:
            continue
        members_sorted = sorted(
            members,
            key=lambda m: (
                -(m.get("wishlistScore") or 0),
                0 if (m.get("wishlist") or {}).get("tier") == "god" else 1,
                -(m.get("power") or 0),
                m.get("name") or "",
            ),
        )
        tiers = {(m.get("wishlist") or {}).get("tier") or "none" for m in members_sorted}
        pieces = []
        for m in members_sorted:
            wl = m.get("wishlist") or {}
            pieces.append(
                {
                    "itemHash": m["itemHash"],
                    "itemInstanceId": m["itemInstanceId"],
                    "name": m.get("name") or "Unknown",
                    "icon": m.get("icon"),
                    "slot": m.get("slot"),
                    "tier": m.get("tier"),
                    "isExotic": bool(m.get("isExotic")),
                    "location": m.get("location"),
                    "characterId": m.get("characterId"),
                    "power": m.get("power"),
                    "isMasterwork": bool(m.get("isMasterwork")),
                    "damageIcon": m.get("damageIcon"),
                    "damageName": m.get("damageName"),
                    "wishlist": {
                        "is_wishlisted": bool(wl.get("is_wishlisted")),
                        "matched_perks": int(wl.get("matched_perks") or 0),
                        "needed_perks": int(wl.get("needed_perks") or 0),
                        "notes": wl.get("notes"),
                        "tier": wl.get("tier") or "none",
                    },
                    "wishlistScore": m.get("wishlistScore") or 0,
                }
            )
        groups.append(
            {
                "itemHash": item_hash,
                "name": members_sorted[0].get("name") or "Unknown",
                "icon": members_sorted[0].get("icon"),
                "slot": members_sorted[0].get("slot"),
                "count": len(pieces),
                "hasGodRoll": "god" in tiers,
                "wishlistDiffers": len(tiers) > 1,
                "pieces": pieces,
            }
        )

    groups.sort(key=lambda g: (-int(g["hasGodRoll"]), -g["count"], g["name"] or ""))
    return {
        "ok": True,
        "scanned": len(weapons),
        "groupCount": len(groups),
        "groups": groups,
    }


async def scan_vault_clean() -> dict:
    """Armor + weapon dupe scan for vault cleaning."""
    import asyncio

    membership, normalized, raw = await profile_svc.get_profile_bundle_cached()
    armor = await asyncio.to_thread(find_armor_dupes, raw)
    weapons = find_weapon_dupes(normalized.get("items") or [])
    return {
        "ok": True,
        "membership": membership,
        "armor": armor,
        "weapons": weapons,
    }
