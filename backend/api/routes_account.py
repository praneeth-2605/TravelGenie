"""Account routes: sign-up, login (password or Google), profile and settings."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from backend import auth, db, history
from backend.config import settings
from backend.rag.store import get_store

router = APIRouter(prefix="/api")


def _email(value: str) -> str:
    try:
        return validate_email(value, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise HTTPException(422, str(exc)) from exc


def _me(user) -> dict:
    return {"user": db.public_user(user), "settings": db.get_settings(user["id"])}


# ------------------------------------------------------------------ auth
@router.get("/auth/config")
def auth_config():
    return {"google_client_id": settings.google_client_id, "contact_email": settings.contact_email}


class SignupBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    accept_terms: bool = False


@router.post("/auth/signup")
def signup(body: SignupBody, response: Response):
    if not body.accept_terms:
        raise HTTPException(422, "Please accept the Terms of Use and Privacy Policy to create an account.")
    email = _email(body.email)
    auth.validate_password(body.password)
    if db.user_by_email(email):
        raise HTTPException(409, "An account with this email already exists. Try logging in.")
    user = db.create_user(email, body.name.strip(), password_hash=auth.hash_password(body.password))
    auth.issue_session(response, user)
    return _me(user)


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


@router.post("/auth/login")
def login(body: LoginBody, response: Response):
    user = auth.check_login(body.email.strip(), body.password)
    if not user:
        raise HTTPException(401, "Incorrect email or password.")
    auth.issue_session(response, user)
    return _me(user)


class GoogleBody(BaseModel):
    credential: str = Field(min_length=10, max_length=5000)


@router.post("/auth/google")
def google_login(body: GoogleBody, response: Response):
    claims = auth.verify_google_credential(body.credential)
    sub, email = claims["sub"], _email(claims["email"])
    user = db.user_by_google(sub)
    if not user:
        existing = db.user_by_email(email)
        if existing:
            # Same verified email: link Google to the existing account.
            db.update_user(existing["id"], google_sub=sub,
                           avatar_url=existing["avatar_url"] or claims.get("picture"))
            user = db.user_by_id(existing["id"])
        else:
            user = db.create_user(email, claims.get("name") or email.split("@")[0],
                                  google_sub=sub, avatar_url=claims.get("picture"))
    auth.issue_session(response, user)
    return _me(user)


@router.post("/auth/logout")
def logout(response: Response):
    auth.clear_session(response)
    return {"ok": True}


@router.post("/auth/logout-all")
def logout_all(response: Response, user=Depends(auth.current_user)):
    db.update_user(user["id"], token_version=user["token_version"] + 1)
    auth.clear_session(response)
    return {"ok": True}


@router.get("/auth/me")
def me(user=Depends(auth.current_user)):
    return _me(user)


# ------------------------------------------------------------------ profile
class ProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.put("/account/profile")
def update_profile(body: ProfileBody, user=Depends(auth.current_user)):
    db.update_user(user["id"], name=body.name.strip())
    return _me(db.user_by_id(user["id"]))


class PasswordBody(BaseModel):
    current_password: str | None = Field(None, max_length=200)
    new_password: str = Field(max_length=200)


@router.put("/account/password")
def change_password(body: PasswordBody, response: Response, user=Depends(auth.current_user)):
    # Google-only accounts may set a first password without a current one.
    if user["password_hash"] and not auth.verify_password(body.current_password or "", user["password_hash"]):
        raise HTTPException(403, "Your current password is incorrect.")
    auth.validate_password(body.new_password)
    db.update_user(user["id"], password_hash=auth.hash_password(body.new_password),
                   token_version=user["token_version"] + 1)
    fresh = db.user_by_id(user["id"])
    auth.issue_session(response, fresh)  # keep this device signed in
    return {"ok": True}


class DeleteBody(BaseModel):
    confirm: Literal["DELETE"]


@router.get("/account/export")
async def export_account(user=Depends(auth.current_user)):
    """Everything we hold about this user, as one JSON file (right to access)."""
    from langchain_core.messages import BaseMessage

    trips = []
    for summary in await asyncio.to_thread(db.list_trips, user["id"]):
        trip = await asyncio.to_thread(db.get_trip, user["id"], summary["id"])
        async with history.checkpointer() as saver:
            snap = await saver.aget({"configurable": {"thread_id": summary["id"]}})
        messages = (snap or {}).get("channel_values", {}).get("messages", []) if snap else []
        trip["chat"] = [{"role": "user" if m.type == "human" else "assistant", "content": m.content}
                        for m in messages if isinstance(m, BaseMessage) and m.type in ("human", "ai")]
        trip.pop("share_token", None)
        trips.append(trip)
    store = get_store()
    uploads = [d for d in await asyncio.to_thread(store.documents, user["id"]) if d.get("mine")]
    payload = {
        "exported_at": db.now(),
        "account": db.public_user(user),
        "settings": db.get_settings(user["id"]),
        "trips": trips,
        "uploaded_documents": uploads,
        "usage": {"note": "Daily AI request counts are kept to enforce fair-use limits."},
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="travelgenie-my-data.json"'})


@router.delete("/account")
async def delete_account(body: DeleteBody, response: Response, user=Depends(auth.current_user)):
    """Deletes the account and everything that belongs to it: settings, trips,
    their chat history, and the user's uploaded documents."""
    trip_ids = [t["id"] for t in await asyncio.to_thread(db.list_trips, user["id"])]
    await history.delete_threads(trip_ids)
    await asyncio.to_thread(get_store().delete_where, {"owner": user["id"]})
    await asyncio.to_thread(db.delete_user, user["id"])  # cascades to settings and trips
    auth.clear_session(response)
    return {"ok": True}


# ------------------------------------------------------------------ settings
class SettingsBody(BaseModel):
    home_currency: str | None = Field(None, min_length=3, max_length=3)
    travel_style: Literal["budget", "balanced", "luxury"] | None = None
    default_travelers: int | None = Field(None, ge=1, le=20)
    budget_min: float | None = Field(None, ge=0)
    budget_max: float | None = Field(None, ge=0)
    interests: list[str] | None = Field(None, max_length=15)
    dietary: str | None = Field(None, max_length=120)
    pace: Literal["relaxed", "moderate", "packed"] | None = None
    theme: Literal["system", "light", "dark"] | None = None
    home_city: str | None = Field(None, max_length=80)


@router.get("/settings")
def get_settings(user=Depends(auth.current_user)):
    return db.get_settings(user["id"])


@router.put("/settings")
def put_settings(body: SettingsBody, user=Depends(auth.current_user)):
    values = body.model_dump(exclude_unset=True)
    if values.get("home_currency"):
        values["home_currency"] = values["home_currency"].upper()
    if "interests" in values:
        values["interests"] = [i.strip()[:40] for i in values["interests"] or [] if i.strip()]
    lo = values.get("budget_min", None)
    hi = values.get("budget_max", None)
    if lo is not None and hi is not None and lo > hi:
        raise HTTPException(422, "Minimum budget can't be above the maximum.")
    return db.update_settings(user["id"], values)
