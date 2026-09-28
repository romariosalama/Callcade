"""
Everything that happens after the call: the scorecard.

- skill score (0-100) is calculated straight from the transcript, so it's
  the same with or without AI and I can explain every point
- arcade points = outcome + skill + combos + badges, times the difficulty
- coaching comes from the AI when it's on, or simple rules in demo mode
"""

import json
import re

import llm
from engine import WON

FILLERS = ["um", "uh", "you know", "basically", "kinda", "sort of", "literally", "i mean"]
OPEN_Q = re.compile(r"^\W*(what|how|why|walk me through|tell me|help me understand|describe)\b", re.I)
NEXT_STEP = re.compile(
    r"\b(meeting|calendar|schedule|demo|next week|tomorrow|monday|tuesday|wednesday|thursday|friday|"
    r"\d+ minutes|book a|set up a (time|call)|follow[- ]up|invite|next step|sign up|get started|"
    r"move forward|contract|pilot|audit|deep[- ]dive)\b", re.I
)
PERCENT = re.compile(r"(?<![\d.])(\d{1,3})(?:\.\d+)?\s*(%|percent)", re.I)
DISCOUNT_WORDS = ("off", "discount", "knock", "lower", "cut", "reduce", "drop")

# harder characters pay more
MULTIPLIER = {1: 1.0, 2: 1.25, 3: 1.5, 4: 2.0, 5: 2.5}
BOSS_MULTIPLIER = 3.0

OUTCOME_POINTS = {"closed": 300, "meeting_booked": 150, "follow_up": 50, "ended": 0, "live": 0, "hung_up": 0}
UPSELL_POINTS = 150

# id: (name, description, points)
BADGES = {
    "pain_hunter": ("Pain Hunter", "Uncovered every hidden pain", 50),
    "objection_crusher": ("Objection Crusher", "Turned every objection around", 50),
    "held_the_line": ("Held the Line", "Won without offering a discount", 40),
    "great_listener": ("Great Listener", "Talked 45% of the call or less", 30),
    "speed_closer": ("Speed Closer", "Won in 5 turns or fewer", 40),
    "comeback_kid": ("Comeback Kid", "They almost hung up, and you still won", 60),
    "smooth_talker": ("Smooth Talker", "Zero filler words", 20),
    "combo_king": ("Combo King", "Hit a x4 combo", 30),
    "gave_away_the_store": ("Gave Away the Store", "Discounted more than the deal allows", -50),
}


def badge_info(key):
    name, desc, pts = BADGES[key]
    return {"id": key, "name": name, "desc": desc, "points": pts}


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", text) if s.strip()]


def discount_offered(text):
    # biggest % discount offered in a line, like "I can do 20% off" -> 20
    low = text.lower()
    if not any(w in low for w in DISCOUNT_WORDS):
        return 0
    return max((int(n) for n, _ in PERCENT.findall(text) if int(n) <= 100), default=0)


def metrics(call):
    rep = [t for t in call.turns if t.speaker == "rep"]
    buyer = [t for t in call.turns if t.speaker == "buyer"]
    rep_words = sum(len(t.text.split()) for t in rep)
    buyer_words = sum(len(t.text.split()) for t in buyer)

    questions = [q for t in rep for q in sentences(t.text) if q.endswith("?")]
    open_questions = [q for q in questions if OPEN_Q.search(q)]

    fillers = {}
    for t in rep:
        low = t.text.lower()
        for f in FILLERS:
            n = len(re.findall(rf"\b{re.escape(f)}\b", low))
            if n:
                fillers[f] = fillers.get(f, 0) + n

    total_words = rep_words + buyer_words
    return {
        "outcome": call.status,
        "upsold": call.upsold,
        "talk_ratio": round(100 * rep_words / total_words) if total_words else 0,
        "rep_words": rep_words,
        "questions": len(questions),
        "open_questions": len(open_questions),
        "longest_monologue": max((len(t.text.split()) for t in rep), default=0),
        "filler_words": fillers,
        "filler_count": sum(fillers.values()),
        "asked_for_next_step": any(NEXT_STEP.search(t.text) and "?" in t.text for t in rep),
        "max_discount_offered": max((discount_offered(t.text) for t in rep), default=0),
        "any_discount_talk": any("discount" in t.text.lower() or discount_offered(t.text) for t in rep),
        "pains_uncovered": len(call.pains_revealed),
        "pains_total": len(call.character["hidden_pains"]),
        "objections_raised": len(call.objections_raised),
        "objections_handled": len(call.objections_handled),
        "mood_start": call.character["starting_mood"],
        "mood_end": call.mood,
        "lowest_mood": call.lowest_mood,
        "mood_timeline": [t.mood for t in call.turns if t.speaker == "buyer"],
        "rep_turns": len(rep),
        "best_combo": call.best_combo,
        "call_points": call.points,
    }


def skill_score(m):
    outcome = {"closed": 25, "meeting_booked": 20, "follow_up": 10, "hung_up": 0}.get(m["outcome"], 3)
    if m["objections_raised"]:
        objections = round(15 * m["objections_handled"] / m["objections_raised"])
    else:
        objections = 0
    ratio = m["talk_ratio"]
    parts = [
        ("Outcome", outcome, 25),
        ("Discovery", round(20 * m["pains_uncovered"] / max(1, m["pains_total"])), 20),
        ("Objection handling", objections, 15),
        ("Questions", 15 if m["open_questions"] >= 3 else 8 if m["open_questions"] >= 1 else 0, 15),
        ("Talk ratio", 10 if 35 <= ratio <= 55 else 5 if 25 <= ratio <= 65 else 0, 10),
        ("Asked for next step", 10 if m["asked_for_next_step"] else 0, 10),
        ("Clean delivery", 5 if m["filler_count"] <= 2 and m["longest_monologue"] <= 70 else 0, 5),
    ]
    return {
        "total": sum(p[1] for p in parts),
        "breakdown": [{"label": p[0], "points": p[1], "max": p[2]} for p in parts],
    }


def earned_badges(call, m):
    won = m["outcome"] in WON
    enough = m["rep_turns"] >= 3  # no free badges for a 1-line call
    got = []
    if m["pains_uncovered"] == m["pains_total"]:
        got.append("pain_hunter")
    if m["objections_raised"] and m["objections_handled"] == m["objections_raised"]:
        got.append("objection_crusher")
    if won and not m["any_discount_talk"]:
        got.append("held_the_line")
    if enough and m["talk_ratio"] <= 45:
        got.append("great_listener")
    if won and m["rep_turns"] <= 5:
        got.append("speed_closer")
    if won and m["lowest_mood"] <= call.character["hang_up_below"] + 10:
        got.append("comeback_kid")
    if enough and m["filler_count"] == 0:
        got.append("smooth_talker")
    if m["best_combo"] >= 4:
        got.append("combo_king")
    if m["max_discount_offered"] > call.character["max_discount_pct"]:
        got.append("gave_away_the_store")
    return got


def points(call, m, skill):
    c = call.character
    mult = BOSS_MULTIPLIER if c.get("boss") else MULTIPLIER[c["stars"]]
    badges = [badge_info(b) for b in earned_badges(call, m)]
    outcome_label = {"closed": "Closed the deal", "meeting_booked": "Booked the meeting",
                     "follow_up": "Warm lead", "hung_up": "They hung up"}.get(m["outcome"], "No deal")
    lines = [{"label": outcome_label, "points": OUTCOME_POINTS.get(m["outcome"], 0)}]
    if m["upsold"]:
        lines.append({"label": "Upsell", "points": UPSELL_POINTS})
    lines.append({"label": f"Skill score ({skill}/100)", "points": skill})
    lines.append({"label": f"Combos during the call (best x{m['best_combo']})", "points": m["call_points"]})
    lines += [{"label": b["name"], "points": b["points"]} for b in badges]
    subtotal = sum(line["points"] for line in lines)

    revenue = 0
    if m["outcome"] == "closed":
        revenue = c["deal_value"]["close"] + (c["deal_value"]["upsell"] if m["upsold"] else 0)
        # discounts come straight out of the deal
        revenue = round(revenue * (100 - min(m["max_discount_offered"], 100)) / 100)

    return {
        "lines": lines,
        "badges": badges,
        "all_badges": [badge_info(k) for k, v in BADGES.items() if v[2] > 0],
        "subtotal": subtotal,
        "multiplier": mult,
        "total": max(0, round(subtotal * mult)),
        "revenue": revenue,
        "won": m["outcome"] in WON,
    }


def key_moments(call, limit=2):
    # the lines that moved the buyer the most, good and bad
    moments = []
    for i, t in enumerate(call.turns):
        if t.speaker != "rep" or i + 1 >= len(call.turns):
            continue
        before = call.turns[i - 1].mood if i > 0 else call.character["starting_mood"]
        reply = call.turns[i + 1]
        moments.append({"you_said": t.text, "buyer_said": reply.text,
                        "mood_change": reply.mood - before, "note": reply.note})
    wins = sorted([m for m in moments if m["mood_change"] > 0], key=lambda m: -m["mood_change"])[:limit]
    losses = sorted([m for m in moments if m["mood_change"] < 0], key=lambda m: m["mood_change"])[:limit]
    return [{**m, "type": "win"} for m in wins] + [{**m, "type": "loss"} for m in losses]


def scorecard(call):
    c = call.character
    m = metrics(call)
    skill = skill_score(m)
    card = {
        "character_id": c["id"],
        "category": c["category"],
        "nickname": c["nickname"],
        "buyer": c["buyer"]["name"],
        "hang_up_below": c["hang_up_below"],
        "metrics": m,
        "score": skill,
        "points": points(call, m, skill["total"]),
        "key_moments": key_moments(call),
        "revealed_pains": [c["hidden_pains"][i] for i in sorted(call.pains_revealed)],
        "missed_pains": [p for i, p in enumerate(c["hidden_pains"]) if i not in call.pains_revealed],
        "transcript": [{"speaker": t.speaker, "text": t.text, "mood": t.mood, "note": t.note} for t in call.turns],
    }
    try:
        card["coaching"] = ai_coaching(call, m) if llm.ai_on() else rule_coaching(m)
    except Exception as e:  # never lose the scorecard because coaching failed
        card["coaching"] = rule_coaching(m)
        card["coaching"]["note"] = f"AI coaching unavailable ({e.__class__.__name__}); showing basic tips."
    return card


def ai_coaching(call, m):
    c = call.character
    transcript = "\n".join(
        f"{'REP' if t.speaker == 'rep' else 'BUYER'} (buyer mood {t.mood}): {t.text}"
        + (f"   [buyer's private reaction: {t.note}]" if t.note else "")
        for t in call.turns
    )
    system = """You are an elite sales coach reviewing a practice call. Be specific, direct, and encouraging,
like a great sales manager. Quote the rep's actual words when you point something out.
Respond with ONLY a JSON object:
{
  "headline": "one sentence verdict on the call",
  "strengths": ["2-3 specific things the rep did well"],
  "improvements": ["2-3 specific, actionable fixes, most important first"],
  "objection_handling": [{"objection": "short name", "grade": "strong" | "okay" | "weak" | "not raised", "tip": "one sentence"}],
  "better_line": {"original": "the rep's weakest line, quoted exactly", "improved": "how a top rep would say it"}
}"""
    prompt = f"""BUYER: {c['nickname']} ({c['buyer']['name']}, {c['buyer']['title']}). {c['traits']}. {c['tagline']}.
GOAL: {c['goal']}
PRODUCT: {c['you_are_selling']}
UPSELL AVAILABLE: {c['upsell']['offer']}
BUYER'S HIDDEN PAINS: {json.dumps(c['hidden_pains'])}
BUYER'S OBJECTIONS: {json.dumps(c['objections'])}

METRICS: {json.dumps({k: v for k, v in m.items() if k != 'mood_timeline'})}

TRANSCRIPT:
{transcript}"""
    return llm.ask_for_json(system, [{"role": "user", "content": prompt}], max_tokens=1200)


def rule_coaching(m):
    strengths, fixes = [], []
    if m["outcome"] == "closed":
        strengths.append("You closed the deal on the call. That's the hardest thing to do in sales.")
    elif m["outcome"] == "meeting_booked":
        strengths.append("You booked the meeting. That's the whole point of the call.")
    if m["upsold"]:
        strengths.append("You landed the upsell too.")
    if m["open_questions"] >= 2:
        strengths.append(f"You asked {m['open_questions']} open-ended questions, which kept the buyer talking.")
    if 35 <= m["talk_ratio"] <= 55:
        strengths.append(f"Good balance: you talked {m['talk_ratio']}% of the time.")
    if m["pains_uncovered"]:
        strengths.append(f"You uncovered {m['pains_uncovered']} of {m['pains_total']} hidden pains.")
    if m["best_combo"] >= 3:
        strengths.append(f"You hit a {m['best_combo']}x combo: several strong lines in a row.")

    if m["max_discount_offered"]:
        fixes.append(f"You offered {m['max_discount_offered']}% off. Trade discounts for something (a longer contract, a case study); never just give them away.")
    left = m["objections_raised"] - m["objections_handled"]
    if left > 0:
        fixes.append(f"You left {left} objection{'s' if left > 1 else ''} unanswered. Acknowledge it, ask why, then answer.")
    if m["talk_ratio"] > 55:
        fixes.append(f"You talked {m['talk_ratio']}% of the call. Aim for under 50%: ask, then listen.")
    if m["open_questions"] < 2:
        fixes.append("Ask more open-ended questions (\"What's your biggest headache with...?\", \"How are you handling...?\").")
    if m["pains_uncovered"] < m["pains_total"]:
        missed = m["pains_total"] - m["pains_uncovered"]
        fixes.append(f"You missed {missed} hidden pain{'s' if missed > 1 else ''}. Dig deeper before pitching.")
    if not m["asked_for_next_step"]:
        fixes.append("You never asked for a clear next step. Always close on a specific day and time.")
    if m["longest_monologue"] > 70:
        fixes.append(f"Your longest turn was {m['longest_monologue']} words. Keep each turn under about 40.")
    if m["filler_count"] > 2:
        fixes.append(f"You used {m['filler_count']} filler words. Pausing sounds more confident than \"um\".")

    return {
        "headline": {
            "closed": "Deal closed on the spot.",
            "meeting_booked": "Meeting booked. Nice work.",
            "follow_up": "No deal yet, but you left them warm. Next time, ask for the meeting.",
            "hung_up": "They hung up. Let's figure out where you lost them.",
        }.get(m["outcome"], "No deal yet. You're closer than you think."),
        "strengths": strengths or ["You picked up the phone. Reps who practice get better fast."],
        "improvements": fixes[:3] or ["Solid call. Try a harder character next."],
        "objection_handling": [],
        "better_line": None,
        "note": "Practice bot mode: this coaching is rule-based. Turn on an AI mode (see docs/AI_SETUP.md) for full AI coaching.",
    }
