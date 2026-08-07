from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..bungie import client, profile as profile_svc

router = APIRouter(prefix="/api/actions", tags=["actions"])

# Destiny 2 character inventory capacity per equipment bucket (excluding equipped).
MAX_CHAR_INVENTORY = 9


class MoveBody(BaseModel):
    itemInstanceId: str
    toStore: str  # "vault" or a characterId


class EquipBody(BaseModel):
    itemInstanceId: str
    characterId: str


class EquipLoadoutBody(BaseModel):
    characterId: str
    itemInstanceIds: list[str]


async def _transfer(item_hash: int, instance_id: str, character_id: str, to_vault: bool, mtype: int):
    await client.post(
        "/Destiny2/Actions/Items/TransferItem/",
        json={
            "itemReferenceHash": item_hash,
            "stackSize": 1,
            "transferToVault": to_vault,
            "itemId": instance_id,
            "characterId": character_id,
            "membershipType": mtype,
        },
    )


async def _equip(instance_id: str, character_id: str, mtype: int):
    await client.post(
        "/Destiny2/Actions/Items/EquipItem/",
        json={"itemId": instance_id, "characterId": character_id, "membershipType": mtype},
    )


async def _load_items() -> list[dict]:
    _, resp = await profile_svc.get_profile_raw()
    return profile_svc.normalize_profile(resp)["items"]


def _find(items: list[dict], instance_id: str) -> Optional[dict]:
    return next((i for i in items if i.get("itemInstanceId") == instance_id), None)


def _inventory_on_character(items: list[dict], character_id: str, kind: str, slot: str) -> list[dict]:
    return [
        i
        for i in items
        if i.get("characterId") == character_id
        and i.get("location") == "character"
        and i.get("kind") == kind
        and i.get("slot") == slot
        and i.get("itemInstanceId")
    ]


async def _make_inventory_space(
    items: list[dict],
    character_id: str,
    kind: Optional[str],
    slot: Optional[str],
    mtype: int,
    *,
    exclude_instance: Optional[str] = None,
) -> Optional[str]:
    """If the character bucket is full (9), vault one item so a transfer can succeed.

    Returns the name of the vaulted item, or None if no vault was needed.
    """
    if not kind or not slot:
        return None
    inv = [
        i
        for i in _inventory_on_character(items, character_id, kind, slot)
        if i["itemInstanceId"] != exclude_instance
    ]
    if len(inv) < MAX_CHAR_INVENTORY:
        return None
    # Prefer vaulting a non-exotic to free a slot.
    inv.sort(key=lambda i: (bool(i.get("isExotic")), i.get("name") or ""))
    victim = inv[0]
    try:
        await _transfer(victim["itemHash"], victim["itemInstanceId"], character_id, True, mtype)
    except client.BungieError as exc:
        raise HTTPException(
            400,
            f"Inventory full and could not vault {victim.get('name')}: {exc}",
        ) from exc
    # Keep local list in sync for subsequent checks in the same request.
    victim["location"] = "vault"
    victim["characterId"] = None
    return victim.get("name") or "an item"


def _find_replacement(items: list[dict], item: dict) -> tuple[Optional[dict], bool]:
    """Find an item to equip in place of `item` so it can be unequipped.

    Returns (replacement, needs_transfer_to_character).
    """
    cands = [
        i
        for i in items
        if i.get("itemInstanceId")
        and i["itemInstanceId"] != item["itemInstanceId"]
        and i.get("kind") == item.get("kind")
        and i.get("slot") == item.get("slot")
        and i.get("location") != "equipped"
    ]
    on_char = [
        c
        for c in cands
        if c.get("characterId") == item.get("characterId") and c["location"] == "character"
    ]
    non_exotic_on_char = [c for c in on_char if not c.get("isExotic")]
    if non_exotic_on_char:
        return non_exotic_on_char[0], False
    if on_char:
        return on_char[0], False
    vault = [c for c in cands if c["location"] == "vault"]
    non_exotic_vault = [c for c in vault if not c.get("isExotic")]
    if non_exotic_vault:
        return non_exotic_vault[0], True
    if vault:
        return vault[0], True
    return None, False


@router.post("/move")
async def move(body: MoveBody) -> dict:
    membership = await profile_svc.get_membership()
    mtype = membership["membership_type"]
    try:
        items = await _load_items()
        item = _find(items, body.itemInstanceId)
        if not item:
            raise HTTPException(404, "Item not found in your inventory. Try Reload.")

        source_char = item.get("characterId")
        target = body.toStore
        bumped: Optional[str] = None

        # No-op cases.
        if target == "vault" and item["location"] == "vault":
            return {"ok": True, "message": f"{item['name']} is already in the Vault."}
        if (
            target != "vault"
            and item["location"] == "character"
            and source_char == target
        ):
            return {"ok": True, "message": f"{item['name']} is already there."}
        if target != "vault" and item["location"] == "equipped" and source_char == target:
            return {"ok": True, "message": f"{item['name']} is already equipped there."}

        # If equipped, swap in a replacement so we can move the original.
        if item["location"] == "equipped":
            repl, needs_transfer = _find_replacement(items, item)
            if not repl:
                raise HTTPException(
                    400,
                    f"No other {item.get('slot')} item available to unequip {item['name']}.",
                )
            if needs_transfer:
                # Pulling a vault item onto the character may need inventory space.
                await _make_inventory_space(
                    items,
                    source_char,
                    item.get("kind"),
                    item.get("slot"),
                    mtype,
                    exclude_instance=item["itemInstanceId"],
                )
                await _transfer(repl["itemHash"], repl["itemInstanceId"], source_char, False, mtype)
            await _equip(repl["itemInstanceId"], source_char, mtype)
            item["location"] = "character"

        if target == "vault":
            await _transfer(item["itemHash"], item["itemInstanceId"], source_char, True, mtype)
            profile_svc.invalidate_profile_cache()
            return {"ok": True, "message": f"Moved {item['name']} to the Vault."}

        # Target is a character — if that bucket is full (9), vault one item first.
        bumped = await _make_inventory_space(
            items,
            target,
            item.get("kind"),
            item.get("slot"),
            mtype,
            exclude_instance=item["itemInstanceId"],
        )

        if item["location"] == "vault":
            await _transfer(item["itemHash"], item["itemInstanceId"], target, False, mtype)
        elif source_char != target:
            # Character-to-character: route through the vault.
            await _transfer(item["itemHash"], item["itemInstanceId"], source_char, True, mtype)
            await _transfer(item["itemHash"], item["itemInstanceId"], target, False, mtype)

        profile_svc.invalidate_profile_cache()
        msg = f"Moved {item['name']}."
        if bumped:
            msg = f"Moved {item['name']} (sent {bumped} to the Vault to make space)."
        return {"ok": True, "message": msg}
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/equip")
async def equip(body: EquipBody) -> dict:
    membership = await profile_svc.get_membership()
    mtype = membership["membership_type"]
    try:
        items = await _load_items()
        item = _find(items, body.itemInstanceId)
        if not item:
            raise HTTPException(404, "Item not found in your inventory. Try Reload.")

        bumped: Optional[str] = None
        # Ensure the item is on the target character first.
        if item["location"] == "vault" or item.get("characterId") != body.characterId:
            bumped = await _make_inventory_space(
                items,
                body.characterId,
                item.get("kind"),
                item.get("slot"),
                mtype,
                exclude_instance=item["itemInstanceId"],
            )
            if item["location"] == "vault":
                await _transfer(item["itemHash"], item["itemInstanceId"], body.characterId, False, mtype)
            elif item.get("characterId") != body.characterId:
                await _transfer(
                    item["itemHash"], item["itemInstanceId"], item["characterId"], True, mtype
                )
                await _transfer(
                    item["itemHash"], item["itemInstanceId"], body.characterId, False, mtype
                )

        await _equip(item["itemInstanceId"], body.characterId, mtype)
        profile_svc.invalidate_profile_cache()
        msg = f"Equipped {item['name']}."
        if bumped:
            msg = f"Equipped {item['name']} (sent {bumped} to the Vault to make space)."
        return {"ok": True, "message": msg}
    except client.BungieError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/equip-loadout")
async def equip_loadout(body: EquipLoadoutBody) -> dict:
    """Move + equip a full set of items onto a character (armor build apply)."""
    if not body.itemInstanceIds:
        raise HTTPException(400, "No items to equip.")
    if not body.characterId:
        raise HTTPException(400, "characterId is required.")

    membership = await profile_svc.get_membership()
    mtype = membership["membership_type"]
    equipped: list[str] = []
    errors: list[str] = []

    try:
        # Fresh inventory each piece so vault/space state stays accurate.
        for instance_id in body.itemInstanceIds:
            items = await _load_items()
            item = _find(items, instance_id)
            if not item:
                errors.append(f"{instance_id}: not found")
                continue
            name = item.get("name") or instance_id
            try:
                if item["location"] == "equipped" and item.get("characterId") == body.characterId:
                    equipped.append(name)
                    continue
                if item["location"] == "vault" or item.get("characterId") != body.characterId:
                    await _make_inventory_space(
                        items,
                        body.characterId,
                        item.get("kind"),
                        item.get("slot"),
                        mtype,
                        exclude_instance=item["itemInstanceId"],
                    )
                    if item["location"] == "vault":
                        await _transfer(
                            item["itemHash"], item["itemInstanceId"], body.characterId, False, mtype
                        )
                    elif item.get("characterId") and item.get("characterId") != body.characterId:
                        await _transfer(
                            item["itemHash"],
                            item["itemInstanceId"],
                            item["characterId"],
                            True,
                            mtype,
                        )
                        await _transfer(
                            item["itemHash"],
                            item["itemInstanceId"],
                            body.characterId,
                            False,
                            mtype,
                        )
                await _equip(item["itemInstanceId"], body.characterId, mtype)
                equipped.append(name)
            except client.BungieError as exc:
                errors.append(f"{name}: {exc}")
    finally:
        profile_svc.invalidate_profile_cache()

    if not equipped and errors:
        raise HTTPException(400, "Failed to equip loadout: " + "; ".join(errors[:3]))

    msg = f"Equipped {len(equipped)} item(s)."
    if errors:
        msg += f" Issues: {'; '.join(errors[:3])}"
    return {"ok": True, "message": msg, "equipped": equipped, "errors": errors}
