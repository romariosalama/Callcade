"""
Ranks, unlocks, and profile stats. All of it is calculated from the results
table, so there's nothing the browser can fake.
"""

import json
from datetime import datetime, timedelta

import db
import engine
import plans
import scoring

CALL_MODES = ("call", "daily", "challenge")
MODE_NAMES = {"gauntlet": "Objection Gauntlet", "mistake": "Spot the Mistake", "clutch": "Clutch Call"}

# what to practice when a skill is your weakest
TIPS = {
    "Discovery": ("You're not finding their hidden problems.",
                  "Ask more open-ended questions before pitching. Skeptical Sam is great practice.", "#/category/tech"),
    "Objection handling": ("Objections are beating you.",
                           "Run the Objection Gauntlet: acknowledge, ask why, then answer.", "#/gauntlet"),
    "Questions": ("You're not asking enough questions.",
                  "Aim for 3+ open-ended questions a call (what, how, why).", "#/category/tech"),
    "Talk ratio": ("You're talking too much.",
                   "Top reps talk less than half the call. Ask, then let them talk.", "#/category/tech"),
    "Asked for next step": ("You're not asking for the meeting.",
                            "End every good call with a specific day and time.", "#/category/tech"),
    "Clean delivery": ("Filler words and long monologues.",
                       "Keep turns short and pause instead of saying um.", "#/category/tech"),
    "Outcome": ("You're not closing.",
                "Once you've handled their objections, ask for the meeting. Try Clutch Call too.", "#/clutch"),
}

RANKS = [
    ("Rookie SDR", 0),
    ("SDR", 500),
    ("Account Executive", 1500),
    ("Senior AE", 4000),
    ("Sales Director", 8000),
    ("VP of Sales", 15000),
    ("Sales Legend", 30000),
]


def rank_for(points):
    i = 0
    while i + 1 < len(RANKS) and points >= RANKS[i + 1][1]:
        i += 1
    name, floor = RANKS[i]
    if i + 1 < len(RANKS):
        next_name, next_at = RANKS[i + 1]
        progress = round(100 * (points - floor) / (next_at - floor))
    else:
        next_name, next_at, progress = None, None, 100
    return {"name": name, "level": i + 1, "next": next_name, "next_at": next_at, "progress": progress}


def beaten_ids(results):
    return {r["character_id"] for r in results if r["mode"] == "call" and r["outcome"] in engine.WON}


def unlocked_ids(results):
    # level 1 of every industry is open. beat a level to open the next one
    beaten = beaten_ids(results)
    open_ids = set()
    for cat in engine.CATEGORIES.values():
        chars = sorted(cat["characters"], key=lambda c: c["level"])
        for i, c in enumerate(chars):
            if i == 0 or chars[i - 1]["id"] in beaten:
                open_ids.add(c["id"])
    return open_ids


def best_scores(results):
    best = {}
    for r in results:
        if r["mode"] == "call":
            best[r["character_id"]] = max(best.get(r["character_id"], 0), r["points"])
    return best


def local_day(iso, tz):
    return datetime.fromisoformat(iso).astimezone(tz).date()


def streaks(results, tz):
    # (current streak, best streak): days in a row with at least one game played
    days = sorted({local_day(r["created_at"], tz) for r in results})
    if not days:
        return 0, 0
    best = run = 1
    for a, b in zip(days, days[1:]):
        run = run + 1 if (b - a).days == 1 else 1
        best = max(best, run)
    today = datetime.now(tz).date()
    if days[-1] < today - timedelta(days=1):
        return 0, best  # missed a day, streak is broken
    current = 1
    for a, b in zip(reversed(days[:-1]), reversed(days[1:])):
        if (b - a).days != 1:
            break
        current += 1
    return current, best


def weak_spot(calls):
    # the skill with the lowest average over the last 10 calls
    totals = {}
    for r in calls[:10]:
        for label, pct in json.loads(r["details"] or "{}").items():
            totals.setdefault(label, []).append(pct)
    if len(calls) < 3 or not totals:
        return None
    averages = {label: sum(v) / len(v) for label, v in totals.items()}
    label = min(averages, key=averages.get)
    if averages[label] >= 80:
        return None  # nothing is really weak
    title, tip, link = TIPS.get(label, ("", "", "#/"))
    return {"skill": label, "score": round(averages[label]), "title": title, "tip": tip, "link": link}


def build_profile(user):
    results = db.user_results(user["id"])
    calls = [r for r in results if r["mode"] in CALL_MODES]
    runs = [r for r in results if r["mode"] == "gauntlet"]
    tz = plans.user_tz(user)
    current_streak, best_streak = streaks(results, tz)

    points = sum(r["points"] for r in results)
    wins = [r for r in calls if r["outcome"] in engine.WON]
    closes = [r for r in calls if r["outcome"] == "closed"]

    badge_counts = {}
    for r in calls:
        for b in json.loads(r["badges"]):
            badge_counts[b] = badge_counts.get(b, 0) + 1

    beaten = beaten_ids(results)
    categories = []
    for cat in engine.CATEGORIES.values():
        ids = [c["id"] for c in cat["characters"]]
        categories.append({"id": cat["id"], "name": cat["name"], "color": cat["color"],
                           "beaten": len([i for i in ids if i in beaten]), "total": len(ids)})

    recent = []
    for r in results[:15]:
        c = engine.CHARACTERS.get(r["character_id"])
        buyer = c["nickname"] if c else MODE_NAMES.get(r["mode"], r["mode"])
        if r["mode"] == "daily":
            buyer = "Daily Challenge: " + buyer
        elif r["mode"] == "challenge":
            buyer = "Friend challenge: " + buyer
        elif r["mode"] == "custom":
            buyer = "Your buyer: " + (r["extra"] or "custom")
        recent.append({
            "mode": r["mode"],
            "category": r["category"],
            "buyer": buyer,
            "outcome": r["outcome"],
            "points": r["points"],
            "revenue": r["revenue"],
            "created_at": r["created_at"],
        })

    all_badges = [{**scoring.badge_info(key), "count": badge_counts.get(key, 0)}
                  for key, (_, _, pts) in scoring.BADGES.items() if pts > 0]

    return {
        "points": points,
        "rank": rank_for(points),
        "revenue": sum(r["revenue"] for r in calls),
        "calls": len(calls),
        "wins": len(wins),
        "closes": len(closes),
        "win_rate": round(100 * len(wins) / len(calls)) if calls else 0,
        "avg_skill": round(sum(r["skill"] for r in calls) / len(calls)) if calls else 0,
        "best_combo": max((r["best_combo"] for r in calls), default=0),
        "gauntlet_best": max((r["points"] for r in runs), default=0),
        "gauntlet_runs": len(runs),
        "streak": current_streak,
        "best_streak": best_streak,
        "played_today": bool(results) and local_day(results[0]["created_at"], tz) == datetime.now(tz).date(),
        "progress": [{"skill": r["skill"], "points": r["points"], "outcome": r["outcome"], "created_at": r["created_at"]}
                     for r in reversed(calls[:20])],
        "weak_spot": weak_spot(calls),
        "best": {m: max((r["points"] for r in results if r["mode"] == m), default=0)
                 for m in ("mistake", "clutch", "gauntlet")},
        "badges": all_badges,
        "categories": categories,
        "recent": recent,
    }
