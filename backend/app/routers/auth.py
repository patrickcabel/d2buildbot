from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from ..bungie import auth, tokens
from ..config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
async def status() -> dict:
    settings = get_settings()
    token = tokens.load_token()
    authenticated = False
    if token is not None:
        authenticated = (not token.is_access_expired) or (
            token.refresh_token is not None and not token.is_refresh_expired
        )
    return {
        "configured": settings.is_bungie_configured,
        "authenticated": authenticated,
        "membershipId": token.membership_id if token else None,
    }


@router.get("/login")
async def login() -> RedirectResponse:
    settings = get_settings()
    if not settings.is_bungie_configured:
        raise HTTPException(500, "Bungie API credentials are not configured. See backend/.env.")
    return RedirectResponse(auth.build_authorize_url())


@router.get("/callback")
async def callback(code: str = Query(...), state: str = Query(...)) -> RedirectResponse:
    settings = get_settings()
    if not auth.consume_state(state):
        raise HTTPException(400, "Invalid OAuth state.")
    try:
        await auth.exchange_code_for_token(code)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Token exchange failed: {exc}") from exc
    return RedirectResponse(f"{settings.frontend_origin}/?login=success")


@router.post("/logout")
async def logout() -> dict:
    tokens.clear_token()
    return {"ok": True}
