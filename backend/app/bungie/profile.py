from __future__ import annotations

from typing import Any, Optional

from ..session import get_session_id
from . import client, manifest

# GetProfile components (numeric).
COMPONENTS = "100,102,200,201,205,300,302,304,305,310"

# Well-known bucket hashes.
BUCKET_KINETIC = 1498876634
BUCKET_ENERGY = 2465295065
BUCKET_POWER = 953998645
BUCKET_HELMET = 3448274439
BUCKET_GAUNTLETS = 3551918588
BUCKET_CHEST = 14239492
BUCKET_LEGS = 20886954
BUCKET_CLASS = 1585787867
BUCKET_LOST_ITEMS = 215593132  # Postmaster
BUCKET_ENGRAMS = 375726501
BUCKET_SPECIAL_ORDERS = 1355129537
BUCKET_MESSAGES = 1367666825

WEAPON_BUCKETS = {BUCKET_KINETIC: "kinetic", BUCKET_ENERGY: "energy", BUCKET_POWER: "power"}
ARMOR_BUCKETS = {
    BUCKET_HELMET: "helmet",
    BUCKET_GAUNTLETS: "gauntlets",
    BUCKET_CHEST: "chest",
    BUCKET_LEGS: "legs",
    BUCKET_CLASS: "class",
}
# Shown above weapons in DIM (per character).
POSTMASTER_BUCKETS = {
    BUCKET_LOST_ITEMS: "postmaster",
    BUCKET_SPECIAL_ORDERS: "postmaster",
    BUCKET_MESSAGES: "postmaster",
}
ENGRAM_BUCKETS = {BUCKET_ENGRAMS: "engrams"}

AMMO_TYPES = {0: "none", 1: "primary", 2: "special", 3: "heavy"}
CLASS_TYPES = {0: "titan", 1: "hunter", 2: "warlock", 3: "unknown"}
TIER_TYPES = {0: "unknown", 2: "basic", 3: "common", 4: "rare", 5: "legendary", 6: "exotic"}


_membership_cache: dict[str, dict] = {}


def _cache_key() -> Optional[str]:
    return get_session_id()


async def get_membership(force: bool = False) -> dict:
    """Return the resolved primary membership for the current session."""
    key = _cache_key()
    if not key:
        raise client.BungieError("Not authenticated with Bungie.", status_code=401)
    if force or key not in _membership_cache:
        _membership_cache[key] = await resolve_membership()
    return _membership_cache[key]


async def resolve_membership() -> dict:
    data = await client.get_current_user_memberships()
    memberships = data.get("destinyMemberships", [])
    if not memberships:
        raise client.BungieError("No Destiny memberships found for this account.", 404)
    primary_id = data.get("primaryMembershipId")
    chosen = next((m for m in memberships if m.get("membershipId") == primary_id), memberships[0])
    return {
        "membership_type": chosen["membershipType"],
        "membership_id": chosen["membershipId"],
        "display_name": chosen.get("displayName"),
        "bungie_global_display_name": data.get("bungieNetUser", {}).get("displayName"),
    }


async def get_profile_raw() -> tuple[dict, dict]:
    membership = await get_membership()
    resp = await client.get(
        f"/Destiny2/{membership['membership_type']}/Profile/{membership['membership_id']}/",
        params={"components": COMPONENTS},
        authed=True,
    )
    return membership, resp


# Short-lived cache so inventory / caps / solve / dupes share one Bungie+normalize pass.
# session_id -> (ts, membership, normalized, raw)
_profile_cache: dict[str, tuple[float, dict, dict, dict]] = {}
_PROFILE_CACHE_TTL = 90.0


async def get_profile_bundle_cached(force: bool = False) -> tuple[dict, dict, dict]:
    """Return (membership, normalized, raw), cached briefly in memory per session."""
    import time

    key = _cache_key()
    if not key:
        raise client.BungieError("Not authenticated with Bungie.", status_code=401)
    now = time.time()
    cached = _profile_cache.get(key)
    if not force and cached is not None and now - cached[0] < _PROFILE_CACHE_TTL:
        return cached[1], cached[2], cached[3]
    membership, resp = await get_profile_raw()
    # Normalize off the event loop — SQLite/JSON work is CPU-bound.
    import asyncio

    normalized = await asyncio.to_thread(normalize_profile, resp)
    _profile_cache[key] = (now, membership, normalized, resp)
    return membership, normalized, resp


async def get_normalized_profile_cached(force: bool = False) -> dict:
    """Return normalize_profile(get_profile_raw()), cached briefly in memory."""
    _membership, normalized, _raw = await get_profile_bundle_cached(force=force)
    return normalized


async def get_profile_raw_cached(force: bool = False) -> tuple[dict, dict]:
    membership, _normalized, raw = await get_profile_bundle_cached(force=force)
    return membership, raw


def invalidate_profile_cache(session_id: Optional[str] = None) -> None:
    """Drop profile cache for one session, or all sessions if none specified."""
    if session_id:
        _profile_cache.pop(session_id, None)
        _membership_cache.pop(session_id, None)
        return
    key = _cache_key()
    if key:
        _profile_cache.pop(key, None)
        _membership_cache.pop(key, None)
    else:
        _profile_cache.clear()
        _membership_cache.clear()


def invalidate_all_profile_caches() -> None:
    _profile_cache.clear()
    _membership_cache.clear()


def get_cached_membership() -> Optional[dict]:
    key = _cache_key()
    if not key:
        return None
    cached = _profile_cache.get(key)
    if cached is None:
        return None
    return cached[1]


async def get_characters_fast() -> tuple[dict, list[dict]]:
    """Character list without pulling inventory components when possible."""
    import time

    key = _cache_key()
    if not key:
        raise client.BungieError("Not authenticated with Bungie.", status_code=401)
    now = time.time()
    cached = _profile_cache.get(key)
    if cached is not None and now - cached[0] < _PROFILE_CACHE_TTL:
        return cached[1], cached[2].get("characters") or []

    membership = await get_membership()
    # 100 Profiles, 200 Characters — enough for class/light/emblem.
    resp = await client.get(
        f"/Destiny2/{membership['membership_type']}/Profile/{membership['membership_id']}/",
        params={"components": "100,200"},
        authed=True,
    )
    return membership, extract_characters(resp)


def _bungie_icon(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path if path.startswith("http") else "https://www.bungie.net" + path


def _is_applied_ornament_plug(pdef: dict) -> bool:
    """True when a socketed plug is a real weapon/armor ornament (not Default/empty)."""
    plug = pdef.get("plug") or {}
    if plug.get("isDummyPlug"):
        return False
    name = ((pdef.get("displayProperties") or {}).get("name") or "").strip().lower()
    if not name or name.startswith("default"):
        return False
    cat = (plug.get("plugCategoryIdentifier") or "").lower()
    type_name = (pdef.get("itemTypeDisplayName") or "").lower()
    if "ornament" in cat or "ornament" in type_name:
        return True
    # Modern transmog: armor_skins_* and weapon *_skins (not empty placeholders).
    if "armor_skins" in cat and "empty" not in cat:
        return True
    if "_skins" in cat and "empty" not in cat:
        return True
    return False


def _resolve_ornament_icon(
    item: dict, socket_plug_hashes: Optional[list[int]] = None
) -> tuple[Optional[str], bool]:
    """Return (icon_url, has_ornament) for an applied ornament / transmog style.

    Prefer Bungie's overrideStyleItemHash (what DIM uses), then scan cosmetics plugs.
    """
    override_hash = item.get("overrideStyleItemHash")
    if override_hash:
        try:
            odef = manifest.get_item(int(override_hash))
        except (TypeError, ValueError):
            odef = None
        if odef and not (odef.get("plug") or {}).get("isDummyPlug"):
            icon = _bungie_icon((odef.get("displayProperties") or {}).get("icon"))
            if icon:
                return icon, True

    for ph in socket_plug_hashes or []:
        pdef = manifest.get_item(int(ph)) if ph else None
        if not pdef or not _is_applied_ornament_plug(pdef):
            continue
        icon = _bungie_icon((pdef.get("displayProperties") or {}).get("icon"))
        if icon:
            return icon, True
    return None, False


def _enrich_item(item: dict, location: str, character_id: Optional[str], item_components: dict) -> Optional[dict]:
    item_hash = item.get("itemHash")
    definition = manifest.get_item(item_hash) if item_hash else None
    if not definition:
        return None

    dp = definition.get("displayProperties") or {}
    inv = definition.get("inventory") or {}
    # Live bucketHash is where the item currently sits (e.g. Postmaster).
    # Fall back to the definition's default bucket for vault/equipped.
    raw_bucket = item.get("bucketHash")
    try:
        bucket = int(raw_bucket) if raw_bucket is not None else inv.get("bucketTypeHash")
    except (TypeError, ValueError):
        bucket = inv.get("bucketTypeHash")
    equipping = definition.get("equippingBlock") or {}
    item_type = definition.get("itemType", 0)

    slot: Optional[str] = None
    kind: Optional[str] = None
    # Current location buckets first — postmaster/engrams override the item's default type.
    if bucket in POSTMASTER_BUCKETS:
        slot = "postmaster"
        kind = "postmaster"
    elif bucket in ENGRAM_BUCKETS or item_type == 8:  # DestinyItemType.Engram
        slot = "engrams"
        kind = "engram"
    elif bucket in WEAPON_BUCKETS:
        slot = WEAPON_BUCKETS[bucket]
        kind = "weapon"
    elif bucket in ARMOR_BUCKETS:
        slot = ARMOR_BUCKETS[bucket]
        kind = "armor"
    else:
        # Equipped / vault items often lack a useful live bucket — use definition default.
        def_bucket = inv.get("bucketTypeHash")
        if def_bucket in WEAPON_BUCKETS:
            slot = WEAPON_BUCKETS[def_bucket]
            kind = "weapon"
        elif def_bucket in ARMOR_BUCKETS:
            slot = ARMOR_BUCKETS[def_bucket]
            kind = "armor"

    tier = (definition.get("inventory") or {}).get("tierType", 0)
    # DestinyItemState bit flags: 1 Locked, 2 Tracked, 4 Masterwork, 8 Crafted, 16 Highlighted.
    state = item.get("state", 0) or 0
    icon = _bungie_icon(dp.get("icon"))
    # Ornament / transmog: swap the tile icon for the applied style (DIM behavior).
    ornament_icon, has_ornament = _resolve_ornament_icon(item)
    if ornament_icon:
        icon = ornament_icon

    result: dict[str, Any] = {
        "itemHash": item_hash,
        "itemInstanceId": item.get("itemInstanceId"),
        "name": dp.get("name"),
        "icon": icon,
        "hasOrnament": has_ornament,
        "itemType": item_type,
        "itemTypeName": definition.get("itemTypeDisplayName"),
        "kind": kind,
        "slot": slot,
        "tierType": tier,
        "tier": TIER_TYPES.get(tier, "unknown"),
        "isExotic": tier == 6,
        "state": state,
        "isMasterwork": bool(state & 4),
        "isCrafted": bool(state & 8),
        "ammoType": AMMO_TYPES.get(equipping.get("ammoType", 0), "none"),
        "damageType": None,
        "classType": CLASS_TYPES.get(definition.get("classType", 3), "unknown"),
        "location": location,
        "characterId": character_id,
        "damageIcon": None,
        "damageName": None,
        "stats": None,
        "perks": None,
    }

    instance_id = item.get("itemInstanceId")
    if instance_id:
        instances = (item_components.get("instances") or {}).get("data", {})
        stats = (item_components.get("stats") or {}).get("data", {})
        sockets = (item_components.get("sockets") or {}).get("data", {})

        inst = instances.get(instance_id)
        if inst:
            result["power"] = (inst.get("primaryStat") or {}).get("value")
            dmg = inst.get("damageType")
            if dmg is not None:
                result["damageType"] = dmg
            dmg_hash = inst.get("damageTypeHash")
            if dmg_hash and dmg not in (None, 0, 1):  # skip None/Kinetic (no element icon)
                ddef = manifest.get_definition("DestinyDamageTypeDefinition", dmg_hash)
                if ddef:
                    dp2 = ddef.get("displayProperties") or {}
                    if dp2.get("icon"):
                        result["damageIcon"] = "https://www.bungie.net" + dp2["icon"]
                    result["damageName"] = dp2.get("name")

        stat_block = stats.get(instance_id)
        if stat_block:
            result["stats"] = {
                sh: sv.get("value") for sh, sv in (stat_block.get("stats") or {}).items()
            }

        socket_block = sockets.get(instance_id)
        if socket_block:
            plug_hashes = [
                s.get("plugHash")
                for s in socket_block.get("sockets", [])
                if s.get("plugHash") and s.get("isEnabled", True)
            ]
            result["perks"] = plug_hashes
            # Fallback when overrideStyleItemHash is missing (some skin plugs).
            if not has_ornament:
                orn_icon, orn = _resolve_ornament_icon(item, plug_hashes)
                if orn and orn_icon:
                    result["icon"] = orn_icon
                    result["hasOrnament"] = True
    return result


def extract_characters(resp: dict) -> list[dict]:
    """Lightweight character list (no item enrichment)."""
    characters_data = (resp.get("characters") or {}).get("data", {})
    characters = []
    for char_id, char in characters_data.items():
        characters.append(
            {
                "characterId": char_id,
                "classType": CLASS_TYPES.get(char.get("classType", 3), "unknown"),
                "light": char.get("light"),
                "emblemPath": ("https://www.bungie.net" + char["emblemBackgroundPath"])
                if char.get("emblemBackgroundPath")
                else None,
            }
        )
    return characters


def normalize_profile(resp: dict) -> dict:
    item_components = resp.get("itemComponents", {})
    characters = extract_characters(resp)

    # Prefetch all item / plug / damage defs in a few SQLite queries instead of
    # opening a connection per hash (dominant cost on large vaults).
    item_hashes: set[int] = set()
    plug_hashes: set[int] = set()
    damage_hashes: set[int] = set()

    def _collect(items: Optional[list]) -> None:
        for it in items or []:
            h = it.get("itemHash")
            if h is not None:
                try:
                    item_hashes.add(int(h))
                except (TypeError, ValueError):
                    pass
            o = it.get("overrideStyleItemHash")
            if o is not None:
                try:
                    item_hashes.add(int(o))
                except (TypeError, ValueError):
                    pass

    _collect(((resp.get("profileInventory") or {}).get("data") or {}).get("items"))
    for block in ((resp.get("characterInventories") or {}).get("data") or {}).values():
        _collect(block.get("items"))
    for block in ((resp.get("characterEquipment") or {}).get("data") or {}).values():
        _collect(block.get("items"))

    sockets = ((item_components.get("sockets") or {}).get("data") or {})
    for block in sockets.values():
        for sock in (block or {}).get("sockets") or []:
            ph = sock.get("plugHash")
            if ph:
                try:
                    plug_hashes.add(int(ph))
                except (TypeError, ValueError):
                    pass

    instances = ((item_components.get("instances") or {}).get("data") or {})
    for inst in instances.values():
        dh = inst.get("damageTypeHash")
        if dh:
            try:
                damage_hashes.add(int(dh))
            except (TypeError, ValueError):
                pass

    if item_hashes or plug_hashes:
        manifest.get_definitions(
            "DestinyInventoryItemDefinition", list(item_hashes | plug_hashes)
        )
    if damage_hashes:
        manifest.get_definitions("DestinyDamageTypeDefinition", list(damage_hashes))

    items: list[dict] = []

    for it in (resp.get("profileInventory") or {}).get("data", {}).get("items", []):
        enriched = _enrich_item(it, "vault", None, item_components)
        if enriched:
            items.append(enriched)

    char_inv = (resp.get("characterInventories") or {}).get("data", {})
    for char_id, block in char_inv.items():
        for it in block.get("items", []):
            enriched = _enrich_item(it, "character", char_id, item_components)
            if enriched:
                items.append(enriched)

    char_equip = (resp.get("characterEquipment") or {}).get("data", {})
    for char_id, block in char_equip.items():
        for it in block.get("items", []):
            enriched = _enrich_item(it, "equipped", char_id, item_components)
            if enriched:
                items.append(enriched)

    # Attach wishlist / god-roll scores to weapons (voltron.txt etc.).
    try:
        from ..builds.wishlist import load_wishlist

        wl = load_wishlist()
        for item in items:
            if item.get("kind") != "weapon":
                continue
            info = wl.score(item.get("itemHash"), item.get("perks") or [])
            item["wishlist"] = info
            # Sort key used by inventory UI: gods first, then near, then power.
            tier_bonus = {"god": 1000, "near": 400, "partial": 100, "none": 0}.get(
                info.get("tier") or "none", 0
            )
            item["wishlistScore"] = (
                tier_bonus
                + int(info.get("matched_perks") or 0) * 10
                + (item.get("power") or 0) / 1000.0
            )
    except Exception:  # noqa: BLE001 — wishlist optional
        pass

    return {"characters": characters, "items": items}


# Stats that are noise in the detail view (hidden/derived).
_HIDDEN_STAT_HASHES = {1935470627}  # Power


async def get_item_detail(instance_id: str, item_hash: Optional[int] = None) -> dict:
    """Fetch a single instanced item and resolve its stats, perks and mods."""
    membership = await get_membership()
    # 307 = ItemCommonData (itemHash/state), 300 instance, 302 perks, 304 stats,
    # 305 sockets, 310 reusable plugs.
    resp = await client.get(
        f"/Destiny2/{membership['membership_type']}/Profile/"
        f"{membership['membership_id']}/Item/{instance_id}/",
        params={"components": "300,302,304,305,307,310"},
        authed=True,
    )

    item_data = (resp.get("item") or {}).get("data") or {}
    resolved_hash = item_data.get("itemHash") or item_hash
    if resolved_hash is not None:
        resolved_hash = int(resolved_hash)

    definition = manifest.get_item(resolved_hash) if resolved_hash else None
    if not definition:
        raise client.BungieError("Item definition not found.", 404)

    dp = definition.get("displayProperties") or {}
    inv = definition.get("inventory") or {}
    tier = inv.get("tierType", 0)
    state = item_data.get("state", 0) or 0

    instance = (resp.get("instance") or {}).get("data") or {}
    live_sockets = ((resp.get("sockets") or {}).get("data") or {}).get("sockets") or []
    plug_hashes = [s["plugHash"] for s in live_sockets if s.get("plugHash")]
    icon = _bungie_icon(dp.get("icon"))
    orn_icon, has_ornament = _resolve_ornament_icon(item_data, plug_hashes)
    if orn_icon:
        icon = orn_icon

    detail: dict[str, Any] = {
        "itemInstanceId": instance_id,
        "itemHash": resolved_hash,
        "name": dp.get("name"),
        "icon": icon,
        "hasOrnament": has_ornament,
        "typeName": definition.get("itemTypeDisplayName"),
        "flavor": dp.get("description") or definition.get("flavorText"),
        "tier": TIER_TYPES.get(tier, "unknown"),
        "isExotic": tier == 6,
        "isMasterwork": bool(state & 4),
        "isCrafted": bool(state & 8),
        "power": (instance.get("primaryStat") or {}).get("value"),
        "damageName": None,
        "damageIcon": None,
        "stats": [],
        "socketGroups": [],
    }

    dmg_hash = instance.get("damageTypeHash")
    if dmg_hash and instance.get("damageType") not in (None, 0, 1):
        ddef = manifest.get_definition("DestinyDamageTypeDefinition", dmg_hash)
        if ddef:
            ddp = ddef.get("displayProperties") or {}
            detail["damageName"] = ddp.get("name")
            if ddp.get("icon"):
                detail["damageIcon"] = "https://www.bungie.net" + ddp["icon"]

    # Stats -> resolve hashes to names.
    stat_data = ((resp.get("stats") or {}).get("data") or {}).get("stats") or {}
    stat_defs = manifest.get_definitions(
        "DestinyStatDefinition", [int(h) for h in stat_data.keys()]
    )
    for stat_hash, entry in stat_data.items():
        h = int(stat_hash)
        if h in _HIDDEN_STAT_HASHES:
            continue
        sdef = stat_defs.get(h)
        name = ((sdef or {}).get("displayProperties") or {}).get("name")
        if not name:
            continue
        detail["stats"].append({"hash": h, "name": name, "value": entry.get("value", 0)})

    # Sockets -> group by socket category (Weapon Perks, Mods, etc.).
    socket_block = definition.get("sockets") or {}
    categories = socket_block.get("socketCategories") or []
    plug_defs = manifest.get_definitions("DestinyInventoryItemDefinition", plug_hashes)

    for cat in categories:
        cat_def = manifest.get_definition(
            "DestinySocketCategoryDefinition", cat.get("socketCategoryHash")
        )
        cat_name = ((cat_def or {}).get("displayProperties") or {}).get("name") or "Other"
        plugs = []
        for idx in cat.get("socketIndexes", []):
            if idx >= len(live_sockets):
                continue
            live = live_sockets[idx]
            if not live.get("isVisible", True):
                continue
            plug_hash = live.get("plugHash")
            if not plug_hash:
                continue
            pdef = plug_defs.get(plug_hash) or manifest.get_item(plug_hash)
            if not pdef:
                continue
            pdp = pdef.get("displayProperties") or {}
            pname = pdp.get("name")
            if not pname:
                continue
            plugs.append(
                {
                    "name": pname,
                    "icon": ("https://www.bungie.net" + pdp["icon"]) if pdp.get("icon") else None,
                    "enabled": live.get("isEnabled", True),
                }
            )
        if plugs:
            detail["socketGroups"].append({"name": cat_name, "plugs": plugs})

    return detail
