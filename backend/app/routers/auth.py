from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import RedirectResponse

from ..bungie import auth, tokens
from ..bungie import profile as profile_svc
from ..config import get_settings
from ..session import (
    attach_session_cookie,
    clear_session_cookie,
    get_session_id,
    new_session_id,
)

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
    session_id = new_session_id()
    try:
        await auth.exchange_code_for_token(code, session_id=session_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Token exchange failed: {exc}") from exc
    profile_svc.invalidate_profile_cache(session_id)
    response = RedirectResponse(f"{settings.resolved_frontend_origin}/?login=success")
    attach_session_cookie(response, session_id)
    return response


@router.post("/logout")
async def logout() -> Response:
    sid = get_session_id()
    tokens.clear_token(sid)
    if sid:
        profile_svc.invalidate_profile_cache(sid)
    response = Response(
        content='{"ok":true}',
        media_type="application/json",
    )
    clear_session_cookie(response)
    return response
