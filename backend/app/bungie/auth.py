from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

import httpx

from ..config import get_settings
from . import tokens

AUTHORIZE_URL = "https://www.bungie.net/en/OAuth/Authorize"
TOKEN_URL = "https://www.bungie.net/Platform/App/OAuth/Token/"

# Signed OAuth `state` lifetime (Render free tier can restart between login + callback).
_STATE_MAX_AGE_SEC = 15 * 60


def _state_secret() -> bytes:
    return get_settings().fernet_key


def _make_state() -> str:
    """Stateless CSRF token: nonce.timestamp.signature (survives restarts/workers)."""
    nonce = secrets.token_urlsafe(16)
    ts = str(int(time.time()))
    payload = f"{nonce}.{ts}".encode()
    sig = hmac.new(_state_secret(), payload, hashlib.sha256).digest()
    return f"{nonce}.{ts}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"


def consume_state(state: str) -> bool:
    parts = (state or "").split(".")
    if len(parts) != 3:
        return False
    nonce, ts_str, sig_b64 = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    if abs(time.time() - ts) > _STATE_MAX_AGE_SEC:
        return False
    payload = f"{nonce}.{ts_str}".encode()
    expected = hmac.new(_state_secret(), payload, hashlib.sha256).digest()
    # Pad for urlsafe_b64decode.
    pad = "=" * (-len(sig_b64) % 4)
    try:
        got = base64.urlsafe_b64decode(sig_b64 + pad)
    except Exception:  # noqa: BLE001
        return False
    return hmac.compare_digest(expected, got)


def build_authorize_url() -> str:
    settings = get_settings()
    params = {
        "client_id": settings.bungie_client_id,
        "response_type": "code",
        "state": _make_state(),
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _basic_auth_header() -> dict[str, str]:
    settings = get_settings()
    raw = f"{settings.bungie_client_id}:{settings.bungie_client_secret}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


async def exchange_code_for_token(code: str) -> None:
    settings = get_settings()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        **_basic_auth_header(),
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.resolved_bungie_redirect_uri,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TOKEN_URL, headers=headers, data=data)
        resp.raise_for_status()
        payload = resp.json()
    _store_payload(payload)


async def refresh_access_token(refresh_token: str) -> None:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        **_basic_auth_header(),
    }
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TOKEN_URL, headers=headers, data=data)
        resp.raise_for_status()
        payload = resp.json()
    _store_payload(payload)


def _store_payload(payload: dict) -> None:
    tokens.save_token(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_in=payload.get("expires_in", 3600),
        refresh_expires_in=payload.get("refresh_expires_in"),
        membership_id=payload.get("membership_id"),
    )


async def get_valid_access_token() -> Optional[str]:
    """Return a usable access token, refreshing if necessary."""
    token = tokens.load_token()
    if token is None:
        return None
    if not token.is_access_expired:
        return token.access_token
    if token.refresh_token and not token.is_refresh_expired:
        await refresh_access_token(token.refresh_token)
        refreshed = tokens.load_token()
        return refreshed.access_token if refreshed else None
    return None
