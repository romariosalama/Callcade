"""
Spot the Mistake: game film review.

You get 3 full sales calls (about 20 lines each). Each one hides 3 or 4 mistakes
the rep made, but most of the rep's lines are actually good. You don't know how
many mistakes there are.

  - Tap a rep line you think is a mistake.
      right: +150, then name WHAT KIND of mistake it was for +100 more
      wrong: -50 and you lose a life (3 lives for the whole run)
  - Hit "Lock it in" when you think you found them all (or the clock runs out).
      every mistake you missed: -75
      found them all with no wrong taps: +300 perfect-call bonus, plus time left x 3
Lose all 3 lives and the run is over.
"""

import json
import random
import time
import uuid
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "data" / "mistakes.json").read_text())
TYPES = DATA["types"]
CALLS = DATA["calls"]
CALLS_PER_RUN = 3
LIVES = 3
TIME_LIMIT = 90  # seconds per call
GRACE = 3

FIND, NAME_IT, WRONG, MISSED, PERFECT, TIME_BONUS = 150, 100, -50, -75, 300, 3

RUNS = {}


def start(user_id=None):
    run = {
        "id": uuid.uuid4().hex[:12],
        "user_id": user_id,
        "calls": random.sample(CALLS, CALLS_PER_RUN),
        "i": 0,
        "lives": LIVES,
        "score": 0,
        "found": {},      # line index -> did they name the type right (None until they answer)
        "wrong": [],
        "started": time.time(),
        "done": False,
        "saved": False,
        "reviews": [],
        "total_found": 0,
        "total_mistakes": 0,
    }
    RUNS[run["id"]] = run
    return run


def call(run):
    return run["calls"][run["i"]]


def mistakes_in(c):
    return {int(k): v for k, v in c["mistakes"].items()}


def current(run):
    c = call(run)
    # the browser gets the call, but not where the mistakes are
    return {
        "call_no": run["i"] + 1, "of": len(run["calls"]), "lives": run["lives"], "score": run["score"],
        "title": c["title"], "category": c["category"], "rep": c["rep"], "buyer": c["buyer"],
        "lines": c["lines"], "time_limit": TIME_LIMIT,
        "found": sorted(run["found"]), "wrong": run["wrong"],
    }


def ready(run):
    run["started"] = time.time()
    return current(run)


def time_left(run):
    return TIME_LIMIT - (time.time() - run["started"])


def tap(run, index):
    if run["done"]:
        raise ValueError("This run is over.")
    c = call(run)
    if not 0 <= index < len(c["lines"]) or c["lines"][index][0] != "rep":
        raise ValueError("Tap one of the rep's lines.")
    if index in run["found"] or index in run["wrong"]:
        raise ValueError("You already tapped that line.")
    if time_left(run) < -GRACE:
        return {"hit": False, "time_up": True, **lock(run)}

    m = mistakes_in(c)
    if index in m:
        run["found"][index] = None
        run["score"] += FIND
        # the right type plus 3 others, shuffled
        others = random.sample([t for t in TYPES if t != m[index]["type"]], 3)
        opts = others + [m[index]["type"]]
        random.shuffle(opts)
        return {"hit": True, "index": index, "points": FIND, "score": run["score"],
                "options": [{"id": t, "label": TYPES[t]} for t in opts]}

    run["wrong"].append(index)
    run["lives"] -= 1
    run["score"] += WRONG
    out = {"hit": False, "index": index, "points": WRONG, "lives": run["lives"], "score": run["score"]}
    if run["lives"] <= 0:
        out.update(lock(run))
    return out


def classify(run, index, kind):
    if index not in run["found"] or run["found"][index] is not None:
        raise ValueError("Find the mistake first.")
    m = mistakes_in(call(run))[index]
    right = kind == m["type"]
    run["found"][index] = right
    if right:
        run["score"] += NAME_IT
    return {"right": right, "type": m["type"], "label": TYPES[m["type"]], "why": m["why"], "fix": m["fix"],
            "points": NAME_IT if right else 0, "score": run["score"]}


def lock(run):
    # end this call: count what they missed, reveal everything, move on
    c = call(run)
    m = mistakes_in(c)
    missed = [i for i in m if i not in run["found"]]
    penalty = MISSED * len(missed)
    bonus = 0
    perfect = not missed and not run["wrong"] and all(run["found"].values())
    if not missed and not run["wrong"]:
        bonus += max(0, round(time_left(run))) * TIME_BONUS
    if perfect:
        bonus += PERFECT
    run["score"] += penalty + bonus
    run["total_found"] += len(m) - len(missed)
    run["total_mistakes"] += len(m)

    review = {
        "title": c["title"], "lines": c["lines"],
        "mistakes": [{"index": i, "type": v["type"], "label": TYPES[v["type"]], "why": v["why"], "fix": v["fix"],
                      "found": i in run["found"], "named": bool(run["found"].get(i))} for i, v in sorted(m.items())],
        "wrong": run["wrong"], "missed": len(missed), "penalty": penalty, "bonus": bonus, "perfect": perfect,
        "score": run["score"],
    }
    run["reviews"].append(review)

    run["i"] += 1
    run["found"], run["wrong"] = {}, []
    if run["lives"] <= 0 or run["i"] >= len(run["calls"]):
        run["done"] = True
    return {"review": review, "done": run["done"]}


def summary(run):
    return {"score": run["score"], "found": run["total_found"], "total": run["total_mistakes"],
            "lives": run["lives"], "calls": len(run["reviews"])}
