"""
Clutch Call: a full sales call with 6 high-pressure moments.

At each moment the buyer says something and you get 4 responses that all sound
reasonable. You have 15 seconds to pick one. Each choice is graded:

  best   +12 deal health, 200 points (+ speed bonus + streak bonus)
  good    +3 deal health,  80 points
  bad    -10 deal health,   0 points
  worst  -22 deal health, -100 points
  froze  -10 deal health, -50 points (ran out of time)

If deal health drops to 10 or lower, the buyer hangs up. After the 6th moment:
  70+ health: you won the call (+400)
  50+ health: they'll "think about it" (+100)
  lower:      you lost them
The options are shuffled every time, and the browser never sees the grades until you pick.
"""

import json
import random
import time
import uuid
from pathlib import Path

SCENARIOS = json.loads((Path(__file__).parent / "data" / "clutch.json").read_text())["scenarios"]
BY_ID = {s["id"]: s for s in SCENARIOS}
TIME_LIMIT = 15
GRACE = 2
START_HEALTH = 45
HANG_UP_AT = 10
HEALTH = {"best": 12, "good": 3, "bad": -10, "worst": -22, "froze": -10}
POINTS = {"best": 200, "good": 80, "bad": 0, "worst": -100, "froze": -50}
OUTCOME_BONUS = {"win": 400, "ok": 100, "lose": 0}
OUTCOME_FOR_DB = {"win": "meeting_booked", "ok": "follow_up", "lose": "hung_up"}

RUNS = {}


def public_list():
    return [{"id": s["id"], "title": s["title"], "category": s["category"], "stars": s["stars"],
             "buyer": s["buyer"], "you": s["you"], "goal": s["goal"]} for s in SCENARIOS]


def start(scenario_id, user_id=None):
    s = BY_ID[scenario_id]
    run = {
        "id": uuid.uuid4().hex[:12], "user_id": user_id, "scenario": s, "i": 0,
        "health": START_HEALTH, "score": 0, "streak": 0, "best_streak": 0, "bests": 0,
        "order": [random.sample(range(4), 4) for _ in s["moments"]],
        "picks": [], "started": time.time(), "done": False, "saved": False, "outcome": None, "hung_up": False,
    }
    RUNS[run["id"]] = run
    return run


def current(run):
    s = run["scenario"]
    m = s["moments"][run["i"]]
    order = run["order"][run["i"]]
    return {
        "moment": run["i"] + 1, "of": len(s["moments"]), "health": run["health"], "score": run["score"],
        "context": m["context"], "time_limit": TIME_LIMIT,
        "options": [{"i": k, "text": m["options"][j]["text"]} for k, j in enumerate(order)],
    }


def ready(run):
    run["started"] = time.time()
    return current(run)


def pick(run, choice):
    if run["done"]:
        raise ValueError("This call is over.")
    s = run["scenario"]
    m = s["moments"][run["i"]]
    elapsed = time.time() - run["started"]
    best = next(o for o in m["options"] if o["grade"] == "best")

    if choice is None or elapsed > TIME_LIMIT + GRACE:
        grade, reaction, why, text = "froze", "...Hello? You still there?", "You froze. On a real call, silence kills momentum.", ""
    else:
        if not 0 <= choice < 4:
            raise ValueError("Pick one of the four lines.")
        o = m["options"][run["order"][run["i"]][choice]]
        grade, reaction, why, text = o["grade"], o["reaction"], o["why"], o["text"]

    points = POINTS[grade]
    speed = 0
    if grade == "best":
        run["streak"] += 1
        run["bests"] += 1
        speed = max(0, min(60, round((TIME_LIMIT - elapsed) * 4)))
        points += speed + min(200, 50 * (run["streak"] - 1))
    else:
        run["streak"] = 0
    run["best_streak"] = max(run["best_streak"], run["streak"])
    run["score"] += points
    run["health"] = max(0, min(100, run["health"] + HEALTH[grade]))

    result = {"grade": grade, "you_said": text, "reaction": reaction, "why": why, "points": points, "speed": speed,
              "streak": run["streak"], "health": run["health"], "score": run["score"],
              "best": None if grade == "best" else {"text": best["text"], "why": best["why"]}}
    run["picks"].append({"moment": run["i"] + 1, **result})
    run["i"] += 1

    if run["health"] <= HANG_UP_AT:
        finish(run, "lose", hung_up=True)
    elif run["i"] >= len(s["moments"]):
        finish(run, "win" if run["health"] >= 70 else "ok" if run["health"] >= 50 else "lose")
    return result


def finish(run, outcome, hung_up=False):
    run["done"] = True
    run["outcome"] = outcome
    run["hung_up"] = hung_up
    run["score"] += OUTCOME_BONUS[outcome]


def summary(run):
    s = run["scenario"]
    ending = "They hung up on you." if run["hung_up"] else s["endings"][run["outcome"]]
    return {"outcome": run["outcome"], "ending": ending, "score": run["score"], "health": run["health"],
            "bests": run["bests"], "moments": len(run["picks"]), "best_streak": run["best_streak"],
            "bonus": OUTCOME_BONUS[run["outcome"]], "picks": run["picks"], "title": s["title"]}

