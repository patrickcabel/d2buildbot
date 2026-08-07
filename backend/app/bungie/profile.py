from __future__ import annotations

from typing import Any, Optional

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

WEAPON_BUCKETS = {BUCKET_KINETIC: "kinetic", BUCKET_ENERGY: "energy", BUCKET_POWER: "power"}
ARMOR_BUCKETS = {
    BUCKET_HELMET: "helmet",
    BUCKET_GAUNTLETS: "gauntlets",
    BUCKET_CHEST: "chest",
    BUCKET_LEGS: "legs",
    BUCKET_CLASS: "class",
}

AMMO_TYPES = {0: "none", 1: "primary", 2: "special", 3: "heavy"}
CLASS_TYPES = {0: "titan", 1: "hunter", 2: "warlock", 3: "unknown"}
TIER_TYPES = {0: "unknown", 2: "basic", 3: "common", 4: "rare", 5: "legendary", 6: "exotic"}


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
    membership = await resolve_membership()
    resp = await client.get(
        f"/Destiny2/{membership['membership_type']}/Profile/{membership['membership_id']}/",
        params={"components": COMPONENTS},
        authed=True,
    )
    return membership, resp


def _enrich_item(item: dict, location: str, character_id: Optional[str], item_components: dict) -> Optional[dict]:
    item_hash = item.get("itemHash")
    definition = manifest.get_item(item_hash) if item_hash else None
    if not definition:
        return None

    dp = definition.get("displayProperties") or {}
    inv = definition.get("inventory") or {}
    bucket = inv.get("bucketTypeHash")
    equipping = definition.get("equippingBlock") or {}
    item_type = definition.get("itemType", 0)

    slot: Optional[str] = None
    kind: Optional[str] = None
    if bucket in WEAPON_BUCKETS:
        slot = WEAPON_BUCKETS[bucket]
        kind = "weapon"
    elif bucket in ARMOR_BUCKETS:
        slot = ARMOR_BUCKETS[bucket]
        kind = "armor"

    tier = (definition.get("inventory") or {}).get("tierType", 0)
    result: dict[str, Any] = {
        "itemHash": item_hash,
        "itemInstanceId": item.get("itemInstanceId"),
        "name": dp.get("name"),
        "icon": ("https://www.bungie.net" + dp["icon"]) if dp.get("icon") else None,
        "itemType": item_type,
        "kind": kind,
        "slot": slot,
        "tierType": tier,
        "tier": TIER_TYPES.get(tier, "unknown"),
        "isExotic": tier == 6,
        "ammoType": AMMO_TYPES.get(equipping.get("ammoType", 0), "none"),
        "damageType": None,
        "classType": CLASS_TYPES.get(definition.get("classType", 3), "unknown"),
        "location": location,
        "characterId": character_id,
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
    return result


def normalize_profile(resp: dict) -> dict:
    item_components = resp.get("itemComponents", {})

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

    return {"characters": characters, "items": items}
