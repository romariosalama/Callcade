"""
Account settings: verify email, forgot/reset password, change password,
timezone, log out everywhere, delete account.
"""

import secrets
from zoneinfo import available_timezones

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

import auth
import db
import mailer
import ratelimit

router = APIRouter(prefix="/api/account")


class Email(BaseModel):
    email: str


class Reset(BaseModel):
    token: str
    password: str


class Token(BaseModel):
    token: str


class ChangePassword(BaseModel):
    current: str
    new: str


class Timezone(BaseModel):
    timezone: str


class DeleteAccount(BaseModel):
    password: str


@router.post("/verify/send")
def resend_verification(request: Request):
    user = auth.require_user(request)
    ratelimit.check(f"verify:{user['id']}", 3, 3600, "You've asked for a few emails already. Check your inbox (and spam).")
    if user["email_verified"]:
        return {"ok": True, "already": True}
    auth.send_verification(user)
    return {"ok": True}


@router.post("/verify")
def verify(req: Token):
    user_id = db.use_token(req.token, "verify")
    if not user_id:
        raise HTTPException(400, "That link is invalid or expired. Send a new one from Settings.")
    db.set_verified(user_id)
    return {"ok": True}


@router.post("/forgot")
def forgot(req: Email, request: Request):
    ratelimit.check("forgot:" + ratelimit.client_ip(request), 5, 3600)
    user = db.find_user(req.email.strip())
    if user:
        token = secrets.token_urlsafe(24)
        db.create_token(token, user["id"], "reset", hours=1)
        mailer.send_reset(user, token)
    # same answer either way so nobody can use this to check who has an account
    return {"ok": True}


@router.post("/reset")
def reset(req: Reset, response: Response):
    if len(req.password) < 8:
        raise HTTPException(400, "Password needs to be at least 8 characters.")
    user_id = db.use_token(req.token, "reset")
    if not user_id:
        raise HTTPException(400, "That reset link is invalid or expired. Ask for a new one.")
    db.set_password(user_id, auth.hash_password(req.password))
    db.delete_all_sessions(user_id)  # log out anyone who might have the old password
    auth.start_session(response, user_id)
    return auth.public_user(db.get_user(user_id))


@router.post("/password")
def change_password(req: ChangePassword, request: Request, response: Response):
    user = auth.require_user(request)
    ratelimit.check(f"pw:{user['id']}", 5, 600)
    if not auth.check_password(req.current, user["password_hash"]):
        raise HTTPException(400, "Your current password is wrong.")
    if len(req.new) < 8:
        raise HTTPException(400, "New password needs to be at least 8 characters.")
    db.set_password(user["id"], auth.hash_password(req.new))
    db.delete_all_sessions(user["id"])
    auth.start_session(response, user["id"])  # keep this device logged in
    return {"ok": True}


@router.post("/timezone")
def set_timezone(req: Timezone, request: Request):
    user = auth.require_user(request)
    if req.timezone not in available_timezones():
        raise HTTPException(400, "Unknown timezone.")
    db.set_timezone(user["id"], req.timezone)
    return {"ok": True}


@router.post("/logout-everywhere")
def logout_everywhere(request: Request, response: Response):
    user = auth.require_user(request)
    db.delete_all_sessions(user["id"])
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.post("/delete")
def delete_account(req: DeleteAccount, request: Request, response: Response):
    user = auth.require_user(request)
    if not auth.check_password(req.password, user["password_hash"]):
        raise HTTPException(400, "Wrong password.")
    db.delete_user(user["id"])
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.get("/settings")
def settings(request: Request):
    user = auth.require_user(request)
    return {"email": user["email"], "email_verified": bool(user["email_verified"]), "timezone": user["timezone"],
            "email_sending": mailer.enabled()}
