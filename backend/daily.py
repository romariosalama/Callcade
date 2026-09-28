"""
Daily Challenge: everyone gets the same buyer each day, one scored try.
The day flips at midnight Pacific time for everybody so it's fair.
"""

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

import engine

DAILY_TZ = ZoneInfo("America/Los_Angeles")


def today():
    return datetime.now(DAILY_TZ).date().isoformat()


def pick(day):
    # same date always gives the same buyer. skip level 1s so it's a real challenge
    options = sorted(c["id"] for c in engine.CHARACTERS.values() if c["level"] >= 2)
    n = int(hashlib.sha256(day.encode()).hexdigest(), 16)
    return engine.CHARACTERS[options[n % len(options)]]
