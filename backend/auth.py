"""
Accounts: sign up, log in, log out.

Passwords are never stored. I store a salted PBKDF2 hash (built into Python's
hashlib) and compare hashes when someone logs in. Logging in gives you a random
session token in an httponly cookie.
"""

import hashlib
import hmac
import os
import re
import secrets
from zoneinfo import available_timezones

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

import db
import engine
import mailer
import ratelimit

router = APIRouter(prefix="/api/auth")

COOKIE = "callcade_session"
# on the live site the login cookie only ever travels over https
SECURE_COOKIE = os.getenv("SITE_URL", "").startswith("https://")
ITERATIONS = 200_000
COLORS = ["#ff6b35", "#34d399", "#f472b6", "#fbbf24", "#60a5fa", "#f87171", "#22d3ee", "#ffd23f"]


def hash_password(password):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"{salt}${h}"


def check_password(password, stored):
    salt, h = stored.split("$")
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return hmac.compare_digest(test, h)


def current_user(request):
    # the logged in user's row, or None for guests
    return db.session_user(request.cookies.get(COOKIE))


def require_user(request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "You need to log in for that.")
    return user


def public_user(row):
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"],
            "color": row["color"], "bio": row["bio"], "plan": row["plan"], "created_at": row["created_at"],
            "email_verified": bool(row["email_verified"]), "is_admin": bool(row["is_admin"])}


def start_session(response, user_id):
    token = secrets.token_urlsafe(32)
    db.create_session(token, user_id)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=SECURE_COOKIE, max_age=60 * 60 * 24 * 30)


def send_verification(user):
    token = secrets.token_urlsafe(24)
    db.create_token(token, user["id"], "verify", hours=48)
    mailer.send_verify(user, token)


class SignupForm(BaseModel):
    username: str
    email: str
    password: str
    display_name: str = ""
    free_category: str = "tech"  # the one industry free accounts get
    timezone: str = "America/Los_Angeles"


class LoginForm(BaseModel):
    login: str  # username or email
    password: str


@router.post("/signup")
def signup(form: SignupForm, request: Request, response: Response):
    ratelimit.check("signup:" + ratelimit.client_ip(request), 5, 3600, "Too many sign ups from here. Try again later.")
    username = form.username.strip()
    email = form.email.strip().lower()
    name = form.display_name.strip() or username

    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
        raise HTTPException(400, "Username has to be 3-20 letters, numbers, or underscores.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "That email doesn't look right.")
    if len(form.password) < 8:
        raise HTTPException(400, "Password needs to be at least 8 characters.")
    if len(name) > 30:
        raise HTTPException(400, "Display name is too long (30 characters max).")
    if form.free_category not in engine.CATEGORIES:
        raise HTTPException(400, "Pick an industry.")
    if db.find_user(username) or db.find_user(email):
        raise HTTPException(400, "That username or email is already taken.")

    tz = form.timezone if form.timezone in available_timezones() else "America/Los_Angeles"
    user_id = db.create_user(username, email, hash_password(form.password), name, secrets.choice(COLORS),
                             form.free_category, tz)
    start_session(response, user_id)
    user = db.get_user(user_id)
    send_verification(user)
    return public_user(user)


@router.post("/login")
def login(form: LoginForm, request: Request, response: Response):
    ip = ratelimit.client_ip(request)
    ratelimit.check("login:" + ip, 20, 60, "Too many login attempts. Wait a minute.")
    ratelimit.check("login:" + form.login.strip().lower(), 5, 60, "Too many login attempts. Wait a minute.")
    user = db.find_user(form.login.strip())
    if not user or not check_password(form.password, user["password_hash"]):
        raise HTTPException(401, "Wrong username/email or password.")
    start_session(response, user["id"])
    return public_user(user)


@router.post("/logout")
def logout(request: Request, response: Response):
    db.delete_session(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    return public_user(user) if user else None
