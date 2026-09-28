"""
The Objection Gauntlet: 10 objections in a row, and the clock gets shorter as you go.

Each answer gets graded 0-10. Points per round:
  score x 10
  + speed bonus (only if the answer was 7+)
  + streak bonus for 8+ answers in a row
The last objection is the boss round and counts double.
You have 3 lives. A weak answer (4 or less) or running out of time costs a life.
Lose all 3 and the run is over.
"""

import json
import random
import re
import time
import uuid
from pathlib import Path

import llm

OBJECTIONS = json.loads((Path(__file__).parent / "data" / "objections.json").read_text())
ROUNDS = 10
TIME_LIMITS = [30, 30, 25, 25, 20, 20, 20, 15, 15, 15]  # seconds per objection, it speeds up
LIVES = 3
STRIKE_AT = 4  # this score or lower costs a life
STREAK_AT = 8
BOSS_ROUND_MULT = 2
GRACE = 3  # a little extra for network lag

RUNS = {}


def pick_objections(category):
    if category == "mixed":
        pool = OBJECTIONS[:]
    else:
        pool = [o for o in OBJECTIONS if o["category"] == category]
        extra = [o for o in OBJECTIONS if o["category"] == "general"]
        random.shuffle(extra)
        pool += extra[: max(0, ROUNDS - len(pool))]
    random.shuffle(pool)
    picked = pool[:ROUNDS]
    picked.sort(key=lambda o: o["difficulty"])  # start easy, end hard
    return picked


def start(category, user_id=None):
    run = {
        "id": uuid.uuid4().hex[:12],
        "user_id": user_id,
        "category": category,
        "items": pick_objections(category),
        "answers": [],
        "streak": 0,
        "best_streak": 0,
        "lives": LIVES,
        "knocked_out": False,
        "total": 0,
        "round_started": time.time(),
        "done": False,
        "saved": False,
    }
    RUNS[run["id"]] = run
    return run


def time_limit(i):
    return TIME_LIMITS[min(i, len(TIME_LIMITS) - 1)]


def is_boss(run, i):
    return i == len(run["items"]) - 1


def current_round(run):
    i = len(run["answers"])
    item = run["items"][i]
    return {"round": i + 1, "of": len(run["items"]), "who": item["who"], "objection": item["objection"],
            "difficulty": item["difficulty"], "time_limit": time_limit(i), "boss": is_boss(run, i),
            "lives": run["lives"]}


def answer(run, text):
    if run["done"]:
        raise ValueError("This run is already over.")
    i = len(run["answers"])
    item = run["items"][i]
    limit = time_limit(i)
    elapsed = time.time() - run["round_started"]
    text = (text or "").strip()[:800]

    if elapsed > limit + GRACE:
        grade = {"score": 0, "verdict": "Out of time.", "good": "", "missed": "You ran out of time. In a real call, silence feels like forever.",
                 "better": item["model_answer"]}
    elif not text:
        grade = {"score": 0, "verdict": "Skipped.", "good": "", "missed": "No answer.", "better": item["model_answer"]}
    elif llm.ai_on():
        grade = ai_grade(item, text)
    else:
        grade = demo_grade(item, text)

    score = max(0, min(10, int(grade.get("score", 0))))
    points = score * 10
    speed_bonus = 0
    if score >= 7:
        speed_bonus = max(0, round(limit - elapsed))
    if score >= STREAK_AT:
        run["streak"] += 1
    else:
        run["streak"] = 0
    run["best_streak"] = max(run["best_streak"], run["streak"])
    streak_bonus = min(50, 10 * (run["streak"] - 1)) if run["streak"] >= 2 else 0

    boss = is_boss(run, i)
    round_points = (points + speed_bonus + streak_bonus) * (BOSS_ROUND_MULT if boss else 1)
    lost_life = score <= STRIKE_AT
    if lost_life:
        run["lives"] -= 1
    run["total"] += round_points
    result = {
        "round": len(run["answers"]) + 1,
        "objection": item["objection"],
        "who": item["who"],
        "answer": text,
        "score": score,
        "verdict": grade.get("verdict", ""),
        "good": grade.get("good", ""),
        "missed": grade.get("missed", ""),
        "better": grade.get("better") or item["model_answer"],
        "seconds": round(min(elapsed, limit), 1),
        "boss": boss,
        "lost_life": lost_life,
        "lives": run["lives"],
        "points": round_points,
        "speed_bonus": speed_bonus,
        "streak": run["streak"],
        "streak_bonus": streak_bonus,
    }
    run["answers"].append(result)
    run["round_started"] = time.time()
    if run["lives"] <= 0:
        run["done"] = True
        run["knocked_out"] = True
    if len(run["answers"]) >= len(run["items"]):
        run["done"] = True
    return result


def summary(run):
    # rounds you never got to count as zeros, so getting knocked out hurts
    scores = [a["score"] for a in run["answers"]]
    avg = sum(scores) / len(run["items"]) if run["items"] else 0
    return {
        "knocked_out": run["knocked_out"],
        "lives": run["lives"],
        "rounds_played": len(run["answers"]),
        "id": run["id"],
        "category": run["category"],
        "total": run["total"],
        "avg_score": round(avg, 1),
        "best_streak": run["best_streak"],
        "answers": run["answers"],
        "grade": letter(avg),
    }


def letter(avg):
    if avg >= 9.3:
        return "S"
    if avg >= 8.5:
        return "A"
    if avg >= 7:
        return "B"
    if avg >= 5.5:
        return "C"
    return "D"


# ---------------- grading ----------------

ACK = ["fair", "understand", "makes sense", "i hear you", "i get it", "totally", "great question",
       "good question", "you're right", "i'm sorry", "that's a good point", "appreciate"]
VALUE = ["cost", "save", "saving", "value", "because", "worth", "instead", "means", "so that", "which"]
STOP = {"about", "their", "there", "would", "could", "should", "thing", "things", "don't", "that's", "what's",
        "which", "question", "answer", "acknowledge", "prospect", "customer", "buyer"}
PUSHY = ["sign today", "right now", "limited time", "you need to", "trust me", "act fast", "last chance"]


def demo_grade(item, text):
    low = text.lower()
    words = len(text.split())
    score = 0
    good, missed = [], []

    if any(a in low for a in ACK):
        score += 3
        good.append("you acknowledged the objection")
    else:
        missed.append("acknowledge the objection before answering")

    if "?" in text:
        score += 3
        good.append("you asked a question to keep them talking")
        if re.search(r"\b(what|how|why)\b", low):
            score += 1
    else:
        missed.append("ask a question to find out what's really behind it")

    if any(v in low for v in VALUE):
        score += 2
        good.append("you tied it back to value")
    else:
        missed.append("connect your answer to what they care about")

    if 12 <= words <= 70:
        score += 1
    elif words > 70:
        missed.append("keep it shorter, under about 60 words")

    if any(p in low for p in PUSHY):
        score -= 3
        missed.append("drop the pressure")

    # is it actually about their objection, or a canned line?
    topic = set(re.findall(r"[a-z']{5,}", (item["objection"] + " " + " ".join(item["hints"])).lower())) - STOP
    said = set(re.findall(r"[a-z']{5,}", low))
    overlap = len(topic & said)
    if overlap == 0:
        score = min(score, 5)
        missed.append("answer their actual objection, not a generic line")
    elif overlap == 1:
        score = min(score, 8)

    # harder objections need the whole package: acknowledge, ask, and give a reason
    if item["difficulty"] >= 3 and not ("?" in text and any(a in low for a in ACK) and any(v in low for v in VALUE)):
        score = min(score, 6)
        missed.append("tough objections need all three: acknowledge, ask, and tie it to value")

    # a canned question with no substance isn't a great answer
    if words < 12:
        score = min(score, 5)

    if words < 6:
        score = min(score, 3)
        missed.append("that was too short to handle it")

    score = max(0, min(10, score))
    verdicts = {10: "Perfect.", 9: "Excellent.", 8: "Really good.", 7: "Good.", 6: "Decent.", 5: "Okay.",
                4: "Needs work.", 3: "Weak.", 2: "Weak.", 1: "Rough.", 0: "Rough."}
    return {
        "score": score,
        "verdict": verdicts[score],
        "good": ("Good: " + ", ".join(good) + ".") if good else "",
        "missed": ("Next time: " + ", ".join(missed) + ".") if missed else "",
        "better": item["model_answer"],
    }


def ai_grade(item, text):
    system = """You are a tough but fair sales coach grading how a salesperson handled one objection.
Be strict. Score 0-10: 10 = what a top rep would say word for word, 8 = strong, 6 = okay but generic,
4 = weak, 0 = harmful or no answer. Most answers should land between 4 and 7. Save 9-10 for answers that
are specific to THIS objection, short enough to say out loud, and would actually work on a real buyer.
A great answer acknowledges the objection, asks a question to find what's behind it, and ties back to
value. Generic lines that could answer any objection score 5 or less. Pushy, defensive, rambling, or
dishonest answers score 3 or less. Harder objections (difficulty 3) need a sharper answer to score well.
Reply with ONLY JSON:
{"score": 0-10, "verdict": "2-4 word verdict", "good": "one sentence on what worked (or empty)",
 "missed": "one sentence on what to fix", "better": "how a top rep would say it, 1-3 spoken sentences"}"""
    prompt = f"""DIFFICULTY: {item['difficulty']}/3
WHO: {item['who']}
OBJECTION: "{item['objection']}"
WHAT A GOOD ANSWER USUALLY INCLUDES: {', '.join(item['hints'])}
THE REP SAID: "{text}\""""
    return llm.ask_for_json(system, [{"role": "user", "content": prompt}], max_tokens=400)
