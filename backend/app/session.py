from __future__ import annotations

import os
import secrets
from contextvars import ContextVar
from typing import Optional

from fastapi import Request, Response

from .config import get_settings

SESSION_COOKIE = "d2_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days

_session_id: ContextVar[Optional[str]] = ContextVar("session_id", default=None)


def get_session_id() -> Optional[str]:
    return _session_id.get()


def set_session_id(session_id: Optional[str]):
    return _session_id.set(session_id)


def reset_session_id(token) -> None:
    _session_id.reset(token)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def cookie_secure() -> bool:
    """Secure cookies on HTTPS (Render); off for local http://localhost:5173."""
    if os.environ.get("RENDER_EXTERNAL_URL"):
        return True
    origin = get_settings().resolved_frontend_origin
    return origin.startswith("https://")


def attach_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, path="/")


async def session_middleware(request: Request, call_next):
    sid = request.cookies.get(SESSION_COOKIE)
    token = set_session_id(sid)
    try:
        return await call_next(request)
    finally:
        reset_session_id(token)
