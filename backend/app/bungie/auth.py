from __future__ import annotations

import base64
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx

from ..config import get_settings
from . import tokens

AUTHORIZE_URL = "https://www.bungie.net/en/OAuth/Authorize"
TOKEN_URL = "https://www.bungie.net/Platform/App/OAuth/Token/"

# In-memory CSRF state store (single-user, local app).
_pending_states: set[str] = set()


def build_authorize_url() -> str:
    settings = get_settings()
    state = secrets.token_urlsafe(24)
    _pending_states.add(state)
    params = {
        "client_id": settings.bungie_client_id,
        "response_type": "code",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def consume_state(state: str) -> bool:
    if state in _pending_states:
        _pending_states.discard(state)
        return True
    return False


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
        "redirect_uri": settings.bungie_redirect_uri,
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
