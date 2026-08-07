from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import DB_PATH, get_settings


def get_connection() -> sqlite3.Connection:
    get_settings()  # ensures data dir exists
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create all application tables if they do not exist."""
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                membership_id TEXT,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at REAL NOT NULL,
                refresh_expires_at REAL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS manifest_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS manifest_defs (
                table_name TEXT NOT NULL,
                hash INTEGER NOT NULL,
                json TEXT NOT NULL,
                PRIMARY KEY (table_name, hash)
            );

            CREATE TABLE IF NOT EXISTS name_index (
                hash INTEGER NOT NULL,
                name TEXT NOT NULL,
                normalized TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                is_exotic INTEGER NOT NULL DEFAULT 0,
                class_type INTEGER NOT NULL DEFAULT 3,
                PRIMARY KEY (hash)
            );
            CREATE INDEX IF NOT EXISTS idx_name_index_norm
                ON name_index (normalized);
            CREATE INDEX IF NOT EXISTS idx_name_index_type
                ON name_index (entity_type);
            CREATE INDEX IF NOT EXISTS idx_name_index_exotic
                ON name_index (is_exotic);

            CREATE TABLE IF NOT EXISTS references_store (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT,
                raw_text TEXT,
                raw_meta TEXT,
                fetched_at REAL
            );

            CREATE TABLE IF NOT EXISTS reference_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                manifest_hash INTEGER NOT NULL,
                name TEXT NOT NULL,
                mention_count INTEGER NOT NULL DEFAULT 1,
                snippet TEXT,
                FOREIGN KEY (reference_id) REFERENCES references_store (id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_reference_facts_hash
                ON reference_facts (manifest_hash);
            CREATE INDEX IF NOT EXISTS idx_reference_facts_ref
                ON reference_facts (reference_id);
            """
        )
