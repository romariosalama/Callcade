"""
Plans and what each one can do. All of this is checked on the server.

  guest: no account. Level 1 of any industry, nothing saved.
  free:  3 levels of one industry you pick, 10 calls and 3 gauntlet runs a day.
  pro:   $6.95/month. Every level in every industry, no daily limits.

Everyone still has to beat each level to unlock the next one.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import db

PRO_PRICE = 6.95

PLANS = {
    "guest": {"name": "Guest", "levels": 1, "calls_per_day": None, "gauntlet_per_day": 0},
    "free": {"name": "Free", "levels": 3, "calls_per_day": 10, "gauntlet_per_day": 3},
    "pro": {"name": "Pro", "levels": 99, "calls_per_day": None, "gauntlet_per_day": None},
}

SWITCH_DAYS = 30  # free users can change their industry once a month


def plan_of(user):
    return user["plan"] if user else "guest"


def access(user, character, unlocked_ids):
    # can this user play this buyer? (True, "") or (False, reason)
    plan = plan_of(user)
    limit = PLANS[plan]["levels"]

    if plan == "guest":
        if character["level"] > 1:
            return False, "signup"
        return True, ""

    if plan == "free" and character["category"] != user["free_category"]:
        return False, "pro"
    if character["level"] > limit:
        return False, "pro"
    if character["id"] not in unlocked_ids:
        return False, "locked"
    return True, ""


def user_tz(user):
    # timezones are checked when they're saved, so this is always a real one
    return ZoneInfo(user["timezone"]) if user else timezone.utc


def start_of_today(user):
    # midnight in the user's own timezone, turned into UTC to compare with the database
    local = datetime.now(user_tz(user)).replace(hour=0, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).isoformat(timespec="seconds")


def used_today(user, kind):
    return db.count_usage(user["id"], kind, start_of_today(user))


def left_today(user, kind):
    # how many calls / gauntlet runs are left today. None means unlimited
    plan = plan_of(user)
    limit = PLANS[plan]["calls_per_day" if kind == "call" else "gauntlet_per_day"]
    if limit is None:
        return None
    if not user:
        return limit
    return max(0, limit - used_today(user, kind))


def can_switch_industry(user):
    if not user["free_category_set_at"]:
        return True, None
    last = datetime.fromisoformat(user["free_category_set_at"])
    next_ok = last + timedelta(days=SWITCH_DAYS)
    return datetime.now(timezone.utc) >= next_ok, next_ok.isoformat(timespec="seconds")


def summary(user):
    plan = plan_of(user)
    out = {
        "plan": plan,
        "name": PLANS[plan]["name"],
        "price": PRO_PRICE,
        "calls_left": left_today(user, "call"),
        "gauntlet_left": left_today(user, "gauntlet"),
        "free_category": user["free_category"] if user else None,
    }
    if user and plan == "free":
        ok, next_ok = can_switch_industry(user)
        out["can_switch"] = ok
        out["switch_after"] = next_ok
    return out
