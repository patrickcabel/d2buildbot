from __future__ import annotations

import json
import time
from typing import Optional

from ..db import db


def upsert_reference(source_type: str, url: str) -> int:
    with db() as conn:
        conn.execute(
            "INSERT INTO references_store (source_type, url, status) VALUES (?, ?, 'pending') "
            "ON CONFLICT(url) DO UPDATE SET source_type=excluded.source_type, status='pending'",
            (source_type, url),
        )
        row = conn.execute("SELECT id FROM references_store WHERE url = ?", (url,)).fetchone()
    return row["id"]


def set_reference_result(
    ref_id: int,
    *,
    title: Optional[str],
    raw_text: Optional[str],
    raw_meta: Optional[dict],
    status: str,
    error: Optional[str] = None,
) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE references_store SET title=?, raw_text=?, raw_meta=?, status=?, error=?, "
            "fetched_at=? WHERE id=?",
            (
                title,
                raw_text,
                json.dumps(raw_meta) if raw_meta is not None else None,
                status,
                error,
                time.time(),
                ref_id,
            ),
        )


def replace_facts(ref_id: int, facts: list[dict]) -> None:
    with db() as conn:
        conn.execute("DELETE FROM reference_facts WHERE reference_id = ?", (ref_id,))
        conn.executemany(
            "INSERT INTO reference_facts "
            "(reference_id, entity_type, manifest_hash, name, mention_count, snippet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    ref_id,
                    f["entity_type"],
                    f["manifest_hash"],
                    f["name"],
                    f["mention_count"],
                    f.get("snippet"),
                )
                for f in facts
            ],
        )


def list_references() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT id, source_type, url, title, status, error, fetched_at, "
            "(SELECT COUNT(*) FROM reference_facts f WHERE f.reference_id = r.id) AS fact_count "
            "FROM references_store r ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_reference(ref_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM references_store WHERE id = ?", (ref_id,)).fetchone()
        if row is None:
            return None
        facts = conn.execute(
            "SELECT entity_type, manifest_hash, name, mention_count, snippet "
            "FROM reference_facts WHERE reference_id = ? ORDER BY mention_count DESC",
            (ref_id,),
        ).fetchall()
    result = dict(row)
    if result.get("raw_meta"):
        try:
            result["raw_meta"] = json.loads(result["raw_meta"])
        except json.JSONDecodeError:
            pass
    result["facts"] = [dict(f) for f in facts]
    return result


def delete_reference(ref_id: int) -> None:
    with db() as conn:
        conn.execute("DELETE FROM references_store WHERE id = ?", (ref_id,))


def facts_for_hashes(hashes: list[int]) -> list[dict]:
    """Aggregate facts across references for the given manifest hashes."""
    if not hashes:
        return []
    with db() as conn:
        placeholders = ",".join("?" * len(hashes))
        rows = conn.execute(
            f"SELECT manifest_hash, entity_type, name, SUM(mention_count) AS mentions, "
            f"COUNT(DISTINCT reference_id) AS sources "
            f"FROM reference_facts WHERE manifest_hash IN ({placeholders}) "
            f"GROUP BY manifest_hash",
            hashes,
        ).fetchall()
    return [dict(r) for r in rows]


def references_mentioning(hashes: list[int]) -> list[dict]:
    """Return references that mention any of the given hashes, with match strength."""
    if not hashes:
        return []
    with db() as conn:
        placeholders = ",".join("?" * len(hashes))
        rows = conn.execute(
            f"SELECT r.id, r.url, r.title, r.source_type, "
            f"SUM(f.mention_count) AS mentions "
            f"FROM references_store r JOIN reference_facts f ON f.reference_id = r.id "
            f"WHERE f.manifest_hash IN ({placeholders}) "
            f"GROUP BY r.id ORDER BY mentions DESC",
            hashes,
        ).fetchall()
    return [dict(r) for r in rows]


def co_mentioned_facts(anchor_hashes: list[int], entity_types: list[str]) -> list[dict]:
    """Find facts of given entity types that co-occur in references mentioning the anchors."""
    if not anchor_hashes:
        return []
    with db() as conn:
        anchor_ph = ",".join("?" * len(anchor_hashes))
        type_ph = ",".join("?" * len(entity_types))
        rows = conn.execute(
            f"SELECT f.manifest_hash, f.entity_type, f.name, "
            f"SUM(f.mention_count) AS mentions, COUNT(DISTINCT f.reference_id) AS sources "
            f"FROM reference_facts f "
            f"WHERE f.reference_id IN ("
            f"  SELECT DISTINCT reference_id FROM reference_facts WHERE manifest_hash IN ({anchor_ph})"
            f") AND f.entity_type IN ({type_ph}) "
            f"AND f.manifest_hash NOT IN ({anchor_ph}) "
            f"GROUP BY f.manifest_hash "
            f"ORDER BY sources DESC, mentions DESC",
            [*anchor_hashes, *entity_types, *anchor_hashes],
        ).fetchall()
    return [dict(r) for r in rows]
