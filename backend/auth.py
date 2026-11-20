"""Authentication: bcrypt passwords, JWT session cookie, Google sign-in.

The session token lives in an httpOnly, SameSite=Lax cookie, so page scripts
can't read it and other sites can't send it with cross-site POSTs. Each user
has a token_version; bumping it (password change, "log out everywhere",
account deletion) invalidates every existing session.
"""

from __future__ import annotations

import secrets
import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response

from backend import db
from backend.config import ROOT, settings

COOKIE = "tg_session"
SESSION_DAYS = 30
ALGORITHM = "HS256"


def _secret() -> str:
    """SECRET_KEY from .env, else one generated once and kept in storage/.
    In production (DATABASE_URL set) SECRET_KEY is required: the server's disk is
    wiped on restart, and a new key would log everyone out."""
    if settings.secret_key:
        return settings.secret_key
    if settings.database_url:
        raise RuntimeError("SECRET_KEY must be set when DATABASE_URL is set (production).")
    path = ROOT / "storage" / "secret.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()


SECRET = _secret()


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


# Constant-time-ish login: always run bcrypt even for unknown emails.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def check_login(email: str, password: str):
    user = db.user_by_email(email)
    ok = verify_password(password, user["password_hash"] if user else _DUMMY_HASH)
    return user if (user and ok) else None


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters.")
    if len(password.encode()) > 72:
        raise HTTPException(422, "Password is too long (max 72 bytes).")
    if password.isalpha() or password.isdigit():
        raise HTTPException(422, "Use a mix of letters and numbers or symbols.")


# ------------------------------------------------------------------ sessions
def issue_session(response: Response, user) -> None:
    payload = {
        "sub": user["id"],
        "ver": user["token_version"],
        "exp": int(time.time()) + SESSION_DAYS * 86400,
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGORITHM)
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, **_cookie_flags())


def _cookie_flags() -> dict:
    # Over HTTPS (production) SameSite=None lets the cookie work when the app is shown
    # inside Hugging Face's page (an iframe); cross-site writes are blocked by the
    # Origin check in the API. Locally, plain Lax.
    if settings.cookie_secure:
        return {"httponly": True, "secure": True, "samesite": "none", "path": "/"}
    return {"httponly": True, "secure": False, "samesite": "lax", "path": "/"}


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, **_cookie_flags())


def current_user_optional(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    user = db.user_by_id(payload.get("sub", ""))
    if not user or user["token_version"] != payload.get("ver"):
        return None
    return user


def current_user(user=Depends(current_user_optional)):
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user


# ------------------------------------------------------------------ Google
def verify_google_credential(credential: str) -> dict:
    """Verify a Google Identity Services ID token and return its claims."""
    if not settings.google_client_id:
        raise HTTPException(400, "Google sign-in is not configured (GOOGLE_CLIENT_ID missing).")
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(credential, g_requests.Request(), settings.google_client_id)
    except ValueError as exc:
        raise HTTPException(401, f"Google sign-in failed: {exc}") from exc
    if not claims.get("email_verified"):
        raise HTTPException(401, "Your Google email address is not verified.")
    return claims
