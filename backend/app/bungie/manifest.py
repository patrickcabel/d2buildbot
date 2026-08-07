from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..db import db
from . import client

# Manifest definition tables we download and cache locally.
NEEDED_TABLES = [
    "DestinyInventoryItemDefinition",
    "DestinyStatDefinition",
    "DestinySandboxPerkDefinition",
    "DestinyDamageTypeDefinition",
    "DestinyInventoryBucketDefinition",
    "DestinyPlugSetDefinition",
    "DestinyItemCategoryDefinition",
    "DestinySocketCategoryDefinition",
]

# DestinyItemType enum values we care about.
ITEM_TYPE_ARMOR = 2
ITEM_TYPE_WEAPON = 3
ITEM_TYPE_SUBCLASS = 16
ITEM_TYPE_MOD = 19


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


async def get_manifest_meta() -> dict:
    return await client.get("/Destiny2/Manifest/")


def stored_version() -> Optional[str]:
    with db() as conn:
        row = conn.execute("SELECT version FROM manifest_meta WHERE id = 1").fetchone()
    return row["version"] if row else None


def _classify(item: dict) -> Optional[str]:
    """Map an InventoryItemDefinition to a build-relevant entity type."""
    item_type = item.get("itemType", 0)
    if item_type == ITEM_TYPE_WEAPON:
        return "weapon"
    if item_type == ITEM_TYPE_ARMOR:
        return "armor"
    if item_type == ITEM_TYPE_SUBCLASS:
        return "subclass"

    plug = item.get("plug") or {}
    category = (plug.get("plugCategoryIdentifier") or "").lower()
    if category:
        if "aspects" in category:
            return "aspect"
        if "fragments" in category:
            return "fragment"
        if "mods" in category or item_type == ITEM_TYPE_MOD:
            return "mod"
        return "perk"

    if item_type == ITEM_TYPE_MOD:
        return "mod"
    return None


def _missing_tables() -> list[str]:
    """Needed tables that have no rows cached (e.g. newly added to NEEDED_TABLES)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT table_name, COUNT(*) AS n FROM manifest_defs GROUP BY table_name"
        ).fetchall()
    present = {r["table_name"] for r in rows if r["n"] > 0}
    return [t for t in NEEDED_TABLES if t not in present]


def _prepare_table(table: str, data: dict) -> tuple[list[tuple], list[tuple]]:
    """Turn a downloaded definition table into DB row batches."""
    rows: list[tuple] = []
    name_rows: list[tuple] = []
    for hash_str, definition in data.items():
        try:
            h = int(hash_str)
        except ValueError:
            continue
        rows.append((table, h, json.dumps(definition)))
        if table != "DestinyInventoryItemDefinition":
            continue
        name = (definition.get("displayProperties") or {}).get("name") or ""
        if not name or definition.get("redacted"):
            continue
        entity = _classify(definition)
        if entity is None:
            continue
        tier = (definition.get("inventory") or {}).get("tierType", 0)
        is_exotic = 1 if tier == 6 else 0
        class_type = definition.get("classType", 3)
        name_rows.append((h, name, _normalize(name), entity, is_exotic, class_type))
    return rows, name_rows


async def sync_manifest(force: bool = False) -> dict:
    """Download and cache needed definition tables if the version changed."""
    import asyncio
    import time

    meta = await get_manifest_meta()
    version = meta["version"]
    if not force and stored_version() == version and not _missing_tables():
        return {"status": "up-to-date", "version": version}

    paths = meta["jsonWorldComponentContentPaths"]["en"]

    # Download + parse outside any DB lock so inventory/auth requests aren't blocked
    # for minutes (holding the lock during network I/O was wedging the server).
    # Parse/serialize in a worker thread so the event loop stays responsive.
    prepared: list[tuple[str, list[tuple], list[tuple]]] = []
    for table in NEEDED_TABLES:
        rel = paths.get(table)
        if not rel:
            continue
        content = await client.get_raw(rel)
        data = await asyncio.to_thread(json.loads, content)
        rows, name_rows = await asyncio.to_thread(_prepare_table, table, data)
        prepared.append((table, rows, name_rows))
        del data  # free large dict before next table

    def _write_db() -> None:
        with db() as conn:
            conn.execute("DELETE FROM manifest_defs")
            conn.execute("DELETE FROM name_index")
            for _table, rows, name_rows in prepared:
                if rows:
                    conn.executemany(
                        "INSERT OR REPLACE INTO manifest_defs (table_name, hash, json) "
                        "VALUES (?, ?, ?)",
                        rows,
                    )
                if name_rows:
                    conn.executemany(
                        "INSERT OR REPLACE INTO name_index "
                        "(hash, name, normalized, entity_type, is_exotic, class_type) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        name_rows,
                    )
            conn.execute(
                "INSERT INTO manifest_meta (id, version, updated_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET version=excluded.version, updated_at=excluded.updated_at",
                (version, time.time()),
            )

    await asyncio.to_thread(_write_db)
    clear_definition_cache()
    return {"status": "synced", "version": version}


# Process-level definition cache — avoid opening SQLite + json.loads per hash
# during profile normalize (thousands of lookups).
_def_cache: dict[tuple[str, int], Optional[dict]] = {}


def clear_definition_cache() -> None:
    _def_cache.clear()


def get_definition(table: str, hash_: int) -> Optional[dict]:
    key = (table, int(hash_))
    if key in _def_cache:
        return _def_cache[key]
    with db() as conn:
        row = conn.execute(
            "SELECT json FROM manifest_defs WHERE table_name = ? AND hash = ?",
            (table, hash_),
        ).fetchone()
    value = json.loads(row["json"]) if row else None
    _def_cache[key] = value
    return value


def get_item(hash_: int) -> Optional[dict]:
    return get_definition("DestinyInventoryItemDefinition", hash_)


def get_definitions(table: str, hashes: list[int]) -> dict[int, dict]:
    if not hashes:
        return {}
    unique = list({int(h) for h in hashes})
    out: dict[int, dict] = {}
    missing: list[int] = []
    for h in unique:
        key = (table, h)
        if key in _def_cache:
            cached = _def_cache[key]
            if cached is not None:
                out[h] = cached
        else:
            missing.append(h)
    if not missing:
        return out
    # SQLite has a practical bind-variable limit; chunk large IN lists.
    chunk = 800
    with db() as conn:
        for i in range(0, len(missing), chunk):
            part = missing[i : i + chunk]
            placeholders = ",".join("?" * len(part))
            rows = conn.execute(
                f"SELECT hash, json FROM manifest_defs "
                f"WHERE table_name = ? AND hash IN ({placeholders})",
                [table, *part],
            ).fetchall()
            found = {int(row["hash"]) for row in rows}
            for row in rows:
                h = int(row["hash"])
                value = json.loads(row["json"])
                _def_cache[(table, h)] = value
                out[h] = value
            for h in part:
                if h not in found:
                    _def_cache[(table, h)] = None
    return out


def search_names(query: str, entity_types: Optional[list[str]] = None, limit: int = 25) -> list[dict]:
    norm = _normalize(query)
    if not norm:
        return []
    sql = "SELECT hash, name, entity_type FROM name_index WHERE normalized LIKE ?"
    args: list[Any] = [f"%{norm}%"]
    if entity_types:
        placeholders = ",".join("?" * len(entity_types))
        sql += f" AND entity_type IN ({placeholders})"
        args.extend(entity_types)
    sql += " LIMIT ?"
    args.append(limit)
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def name_row(hash_: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute(
            "SELECT hash, name, entity_type, is_exotic, class_type FROM name_index WHERE hash = ?",
            (hash_,),
        ).fetchone()
    return dict(row) if row else None


def exotic_names() -> list[dict]:
    """All exotic weapons/armor for query matching."""
    with db() as conn:
        rows = conn.execute(
            "SELECT hash, name, normalized, entity_type, class_type FROM name_index "
            "WHERE is_exotic = 1 AND entity_type IN ('weapon', 'armor')"
        ).fetchall()
    return [dict(r) for r in rows]


def all_names(entity_types: Optional[list[str]] = None) -> list[dict]:
    sql = "SELECT hash, name, normalized, entity_type FROM name_index"
    args: list[Any] = []
    if entity_types:
        placeholders = ",".join("?" * len(entity_types))
        sql += f" WHERE entity_type IN ({placeholders})"
        args.extend(entity_types)
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]
