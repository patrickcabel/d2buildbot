from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from cryptography.fernet import Fernet

from ..config import get_settings
from ..db import db


@dataclass
class StoredToken:
    membership_id: Optional[str]
    access_token: str
    refresh_token: Optional[str]
    expires_at: float
    refresh_expires_at: Optional[float]

    @property
    def is_access_expired(self) -> bool:
        # 60s safety margin.
        return time.time() >= (self.expires_at - 60)

    @property
    def is_refresh_expired(self) -> bool:
        if self.refresh_expires_at is None:
            return True
        return time.time() >= (self.refresh_expires_at - 60)


def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key)


def save_token(
    *,
    access_token: str,
    refresh_token: Optional[str],
    expires_in: float,
    refresh_expires_in: Optional[float],
    membership_id: Optional[str],
) -> None:
    f = _fernet()
    now = time.time()
    enc_access = f.encrypt(access_token.encode()).decode()
    enc_refresh = f.encrypt(refresh_token.encode()).decode() if refresh_token else None
    with db() as conn:
        conn.execute(
            """
            INSERT INTO tokens (id, membership_id, access_token, refresh_token,
                                expires_at, refresh_expires_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                membership_id=excluded.membership_id,
                access_token=excluded.access_token,
                refresh_token=excluded.refresh_token,
                expires_at=excluded.expires_at,
                refresh_expires_at=excluded.refresh_expires_at,
                updated_at=excluded.updated_at
            """,
            (
                membership_id,
                enc_access,
                enc_refresh,
                now + float(expires_in),
                (now + float(refresh_expires_in)) if refresh_expires_in else None,
                now,
            ),
        )


def load_token() -> Optional[StoredToken]:
    with db() as conn:
        row = conn.execute("SELECT * FROM tokens WHERE id = 1").fetchone()
    if row is None:
        return None
    f = _fernet()
    return StoredToken(
        membership_id=row["membership_id"],
        access_token=f.decrypt(row["access_token"].encode()).decode(),
        refresh_token=f.decrypt(row["refresh_token"].encode()).decode()
        if row["refresh_token"]
        else None,
        expires_at=row["expires_at"],
        refresh_expires_at=row["refresh_expires_at"],
    )


def clear_token() -> None:
    with db() as conn:
        conn.execute("DELETE FROM tokens WHERE id = 1")
