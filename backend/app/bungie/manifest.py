from __future__ import annotations

import asyncio
import json
import re
import time
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

# Background sync status (Render free tier kills long HTTP requests / OOMs easy).
_sync_state: dict[str, Any] = {
    "status": "idle",  # idle | running | synced | up-to-date | error
    "version": None,
    "progress": "",
    "error": None,
    "table": None,
    "tableIndex": 0,
    "tableCount": len(NEEDED_TABLES),
}
_sync_task: Optional[asyncio.Task] = None


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


async def get_manifest_meta() -> dict:
    return await client.get("/Destiny2/Manifest/")


def stored_version() -> Optional[str]:
    with db() as conn:
        row = conn.execute("SELECT version FROM manifest_meta WHERE id = 1").fetchone()
    return row["version"] if row else None


def sync_status() -> dict:
    out = dict(_sync_state)
    if out["status"] in ("idle", "error") and out.get("version") is None:
        out["version"] = stored_version()
    return out


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


def _write_table(table: str, rows: list[tuple], name_rows: list[tuple], *, wipe: bool) -> None:
    with db() as conn:
        if wipe:
            conn.execute("DELETE FROM manifest_defs")
            conn.execute("DELETE FROM name_index")
        else:
            conn.execute("DELETE FROM manifest_defs WHERE table_name = ?", (table,))
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


def _set_version(version: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO manifest_meta (id, version, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET version=excluded.version, updated_at=excluded.updated_at",
            (version, time.time()),
        )


def _signed_id_to_hash(signed_id: int) -> int:
    """SQLite stores hashes as signed 32-bit ints; convert to unsigned."""
    h = int(signed_id)
    return h + (1 << 32) if h < 0 else h


def _name_row_from_item(h: int, definition: dict) -> Optional[tuple]:
    name = (definition.get("displayProperties") or {}).get("name") or ""
    if not name or definition.get("redacted"):
        return None
    entity = _classify(definition)
    if entity is None:
        return None
    tier = (definition.get("inventory") or {}).get("tierType", 0)
    is_exotic = 1 if tier == 6 else 0
    class_type = definition.get("classType", 3)
    return (h, name, _normalize(name), entity, is_exotic, class_type)


def _import_mobile_sqlite(sqlite_path: str, tables: list[str], *, full: bool) -> None:
    """Copy definition tables from Bungie's mobile SQLite into our app DB (low RAM)."""
    import sqlite3
    from pathlib import Path

    src_path = Path(sqlite_path)
    src = sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        existing = {
            r[0]
            for r in src.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        with db() as dest:
            if full:
                dest.execute("DELETE FROM manifest_defs")
                dest.execute("DELETE FROM name_index")
            for i, table in enumerate(tables):
                if table not in existing:
                    continue
                _sync_state.update(
                    {
                        "progress": f"Importing {table}…",
                        "table": table,
                        "tableIndex": i + 1,
                        "tableCount": len(tables),
                    }
                )
                if not full:
                    dest.execute("DELETE FROM manifest_defs WHERE table_name = ?", (table,))
                batch_defs: list[tuple] = []
                batch_names: list[tuple] = []
                for row in src.execute(f'SELECT id, json FROM "{table}"'):  # noqa: S608
                    h = _signed_id_to_hash(row["id"])
                    raw = row["json"]
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    batch_defs.append((table, h, raw))
                    if table == "DestinyInventoryItemDefinition":
                        try:
                            definition = json.loads(raw)
                        except json.JSONDecodeError:
                            definition = None
                        if definition:
                            nr = _name_row_from_item(h, definition)
                            if nr:
                                batch_names.append(nr)
                    if len(batch_defs) >= 500:
                        dest.executemany(
                            "INSERT OR REPLACE INTO manifest_defs (table_name, hash, json) "
                            "VALUES (?, ?, ?)",
                            batch_defs,
                        )
                        if batch_names:
                            dest.executemany(
                                "INSERT OR REPLACE INTO name_index "
                                "(hash, name, normalized, entity_type, is_exotic, class_type) "
                                "VALUES (?, ?, ?, ?, ?, ?)",
                                batch_names,
                            )
                        batch_defs.clear()
                        batch_names.clear()
                if batch_defs:
                    dest.executemany(
                        "INSERT OR REPLACE INTO manifest_defs (table_name, hash, json) "
                        "VALUES (?, ?, ?)",
                        batch_defs,
                    )
                if batch_names:
                    dest.executemany(
                        "INSERT OR REPLACE INTO name_index "
                        "(hash, name, normalized, entity_type, is_exotic, class_type) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        batch_names,
                    )
    finally:
        src.close()


async def _sync_via_mobile_sqlite(version: str, mobile_path: str, tables: list[str], *, full: bool) -> None:
    """Stream Bungie's zipped SQLite manifest to disk, then import needed tables."""
    import gc
    import tempfile
    import zipfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="d2manifest_"))
    zip_path = tmp / "world.content.zip"
    try:
        _sync_state["progress"] = "Downloading SQLite manifest…"

        def _prog(n: int) -> None:
            mb = n / (1024 * 1024)
            _sync_state["progress"] = f"Downloading SQLite manifest… {mb:.0f} MB"

        await client.download_to_file(mobile_path, str(zip_path), on_progress=_prog)
        _sync_state["progress"] = "Extracting SQLite manifest…"

        def _extract() -> str:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                if not names:
                    raise RuntimeError("Empty manifest zip")
                zf.extract(names[0], path=tmp)
                return str(tmp / names[0])

        sqlite_file = await asyncio.to_thread(_extract)
        # Free zip bytes on disk ASAP.
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
        gc.collect()

        await asyncio.to_thread(_import_mobile_sqlite, sqlite_file, tables, full=full)
        await asyncio.to_thread(_set_version, version)
        clear_definition_cache()
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


async def _sync_tables(version: str, paths: dict, tables: list[str], *, full: bool) -> None:
    """JSON-component fallback (higher RAM) — one table at a time."""
    import gc

    for i, table in enumerate(tables):
        _sync_state.update(
            {
                "progress": f"Downloading {table}…",
                "table": table,
                "tableIndex": i + 1,
                "tableCount": len(tables),
            }
        )
        rel = paths.get(table)
        if not rel:
            continue
        content = await client.get_raw(rel)
        _sync_state["progress"] = f"Parsing {table}…"
        data = await asyncio.to_thread(json.loads, content)
        del content
        rows, name_rows = await asyncio.to_thread(_prepare_table, table, data)
        del data
        _sync_state["progress"] = f"Writing {table} ({len(rows)} defs)…"
        wipe = full and i == 0
        await asyncio.to_thread(_write_table, table, rows, name_rows, wipe=wipe)
        del rows, name_rows
        gc.collect()

    await asyncio.to_thread(_set_version, version)
    clear_definition_cache()


async def _run_sync(force: bool) -> None:
    try:
        _sync_state.update(
            {
                "status": "running",
                "progress": "Checking manifest version…",
                "error": None,
                "table": None,
            }
        )
        meta = await get_manifest_meta()
        version = meta["version"]
        missing = _missing_tables()
        if not force and stored_version() == version and not missing:
            _sync_state.update(
                {
                    "status": "up-to-date",
                    "version": version,
                    "progress": "Already up to date",
                    "error": None,
                }
            )
            return

        full = force or stored_version() != version
        tables = list(NEEDED_TABLES) if full else missing

        mobile = (meta.get("mobileWorldContentPaths") or {}).get("en")
        if mobile:
            await _sync_via_mobile_sqlite(version, mobile, tables, full=full)
        else:
            paths = meta["jsonWorldComponentContentPaths"]["en"]
            await _sync_tables(version, paths, tables, full=full)

        _sync_state.update(
            {
                "status": "synced",
                "version": version,
                "progress": "Done",
                "error": None,
                "table": None,
            }
        )
    except Exception as exc:  # noqa: BLE001
        _sync_state.update(
            {
                "status": "error",
                "progress": "Failed",
                "error": str(exc) or exc.__class__.__name__,
            }
        )


async def start_sync_manifest(force: bool = False) -> dict:
    """Kick off a background sync and return immediately (avoids proxy timeouts)."""
    global _sync_task
    if _sync_task is not None and not _sync_task.done():
        return sync_status()

    # Fast path: already current — answer without a background task.
    try:
        meta = await get_manifest_meta()
        version = meta["version"]
        if not force and stored_version() == version and not _missing_tables():
            _sync_state.update(
                {
                    "status": "up-to-date",
                    "version": version,
                    "progress": "Already up to date",
                    "error": None,
                }
            )
            return sync_status()
    except Exception:  # noqa: BLE001 — fall through to background (will surface error)
        pass

    _sync_state.update(
        {
            "status": "running",
            "progress": "Starting…",
            "error": None,
            "version": stored_version(),
        }
    )
    _sync_task = asyncio.create_task(_run_sync(force))
    return sync_status()


async def sync_manifest(force: bool = False) -> dict:
    """Compatibility wrapper: start background sync and wait until finished."""
    await start_sync_manifest(force=force)
    while True:
        st = sync_status()
        if st["status"] in ("synced", "up-to-date", "error", "idle"):
            if st["status"] == "error":
                raise RuntimeError(st.get("error") or "Manifest sync failed")
            return {"status": st["status"], "version": st.get("version")}
        await asyncio.sleep(0.5)


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
