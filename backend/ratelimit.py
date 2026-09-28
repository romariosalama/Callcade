"""
Simple in-memory rate limiter. Stops people from hammering the login form or
spamming the AI (which costs money once it's connected).

It forgets everything when the server restarts, which is fine for now. If this
ran on more than one server I'd move it to Redis.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException

_hits = defaultdict(deque)


def check(key, limit, seconds, message="Slow down a little and try again in a minute."):
    now = time.time()
    hits = _hits[key]
    while hits and hits[0] < now - seconds:
        hits.popleft()
    if len(hits) >= limit:
        raise HTTPException(429, message)
    hits.append(now)


def reset():
    _hits.clear()


def client_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
