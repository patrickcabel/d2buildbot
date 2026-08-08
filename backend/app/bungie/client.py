from __future__ import annotations

from typing import Any, Optional

import httpx

from ..config import get_settings
from . import auth

API_ROOT = "https://www.bungie.net/Platform"
BUNGIE_ROOT = "https://www.bungie.net"

_http_client: Optional[httpx.AsyncClient] = None


class BungieError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0), http2=False)
    return _http_client


async def _headers(authed: bool) -> dict[str, str]:
    settings = get_settings()
    headers = {"X-API-Key": settings.bungie_api_key}
    if authed:
        token = await auth.get_valid_access_token()
        if not token:
            raise BungieError("Not authenticated with Bungie.", status_code=401)
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def get(path: str, *, params: Optional[dict] = None, authed: bool = False) -> Any:
    """GET a Platform endpoint and unwrap the standard Bungie response envelope."""
    url = path if path.startswith("http") else f"{API_ROOT}{path}"
    headers = await _headers(authed)
    resp = await _client().get(url, headers=headers, params=params)
    if resp.status_code >= 400:
        raise BungieError(f"Bungie API error {resp.status_code}: {resp.text[:300]}", resp.status_code)
    payload = resp.json()
    if payload.get("ErrorCode", 1) != 1:
        raise BungieError(
            f"Bungie API returned {payload.get('ErrorStatus')}: {payload.get('Message')}",
            502,
        )
    return payload.get("Response")


async def post(path: str, *, json: Optional[dict] = None, authed: bool = True) -> Any:
    """POST to a Platform endpoint and unwrap the standard Bungie response envelope."""
    url = path if path.startswith("http") else f"{API_ROOT}{path}"
    headers = await _headers(authed)
    headers["Content-Type"] = "application/json"
    resp = await _client().post(url, headers=headers, json=json)
    if resp.status_code >= 400:
        # Try to surface Bungie's structured error message.
        try:
            payload = resp.json()
            msg = payload.get("Message") or resp.text[:300]
        except Exception:  # noqa: BLE001
            msg = resp.text[:300]
        raise BungieError(f"Bungie API error {resp.status_code}: {msg}", resp.status_code)
    payload = resp.json()
    if payload.get("ErrorCode", 1) != 1:
        raise BungieError(
            f"{payload.get('ErrorStatus')}: {payload.get('Message')}",
            400,
        )
    return payload.get("Response")


async def get_raw(url: str) -> bytes:
    """Fetch a raw asset (e.g. a manifest content file) from bungie.net."""
    full = url if url.startswith("http") else f"{BUNGIE_ROOT}{url}"
    resp = await _client().get(full, timeout=httpx.Timeout(300.0, connect=30.0))
    if resp.status_code >= 400:
        raise BungieError(f"Failed to fetch {full}: {resp.status_code}", resp.status_code)
    return resp.content


async def get_current_user_memberships() -> Any:
    return await get("/User/GetMembershipsForCurrentUser/", authed=True)
