"""
Build your own buyer.

You describe what you sell and your toughest customer, and this turns it into a
buyer with the same shape as the ones in data/: a personality, 3 hidden pains,
3 objections, a win condition, and so on. With AI on, the AI writes the buyer.
Without AI, it gets filled in from a template so the feature still works.

The game rules (mood caps, objections needed to win) come from the difficulty
you pick, not from the AI, so a custom buyer plays by the same rules as the rest.
"""

import random
import re
import uuid

import llm

TUNING = {
    1: dict(starting_mood=50, hang_up_below=5, meeting_threshold=60, objections_to_win=1, pain_gate=35, patience_words=80, max_turns=18),
    2: dict(starting_mood=42, hang_up_below=10, meeting_threshold=65, objections_to_win=2, pain_gate=40, patience_words=65, max_turns=16),
    3: dict(starting_mood=32, hang_up_below=10, meeting_threshold=68, objections_to_win=2, pain_gate=45, patience_words=55, max_turns=14),
    4: dict(starting_mood=25, hang_up_below=10, meeting_threshold=70, objections_to_win=3, pain_gate=50, patience_words=50, max_turns=14),
    5: dict(starting_mood=20, hang_up_below=12, meeting_threshold=74, objections_to_win=3, pain_gate=55, patience_words=45, max_turns=14),
}
COLORS = [["#a5b4fc", "#4f46e5"], ["#f9a8d4", "#db2777"], ["#6ee7b7", "#059669"], ["#fcd34d", "#d97706"],
          ["#93c5fd", "#2563eb"], ["#fca5a5", "#dc2626"], ["#c4b5fd", "#7c3aed"]]
VOICES = {"male": ["Matthew", "Stephen", "Gregory", "Joey"], "female": ["Joanna", "Danielle", "Kendra", "Ruth"]}
FIRST = {"male": ["Marcus", "Derek", "Luis", "Kevin", "Omar", "Travis"], "female": ["Janet", "Priya", "Monica", "Tasha", "Lauren", "Rosa"]}
LAST = ["Holt", "Ramirez", "Chen", "Walsh", "Patel", "Brooks", "Okafor", "Stone"]


def clean(text, limit):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text[:limit]


def build(sell, customer, difficulty=3, call_type="phone"):
    sell = clean(sell, 600)
    customer = clean(customer, 800)
    if len(sell) < 10 or len(customer) < 10:
        raise ValueError("Tell me a little more about what you sell and who you're selling to.")
    difficulty = max(1, min(5, int(difficulty or 3)))
    call_type = "door" if call_type == "door" else "phone"

    made = None
    if llm.ai_on():
        try:
            made = ai_buyer(sell, customer, difficulty, call_type)
        except Exception:
            made = None  # fall back to the template instead of failing
    if not made:
        made = template_buyer(sell, customer, difficulty)
    return finish(made, sell, difficulty, call_type)


def finish(m, sell, difficulty, call_type):
    # take what the AI (or template) wrote and make it safe to play: every field there, nothing too long
    gender = "female" if str(m.get("gender", "")).lower().startswith("f") else "male"
    b = m.get("buyer") or {}
    name = clean(b.get("name"), 40) or random.choice(FIRST[gender]) + " " + random.choice(LAST)
    first = name.split()[0]
    upsell = m.get("upsell")
    if isinstance(upsell, dict):
        upsell = upsell.get("offer")

    def three(key, fallback):
        items = [clean(x, 220) for x in (m.get(key) or []) if isinstance(x, str) and x.strip()]
        items += [x for x in fallback if x not in items]
        return items[:3]

    c = {
        "id": "custom-" + uuid.uuid4().hex[:10],
        "custom": True,
        "level": 0,
        "nickname": clean(m.get("nickname"), 32) or f"Tough {first}",
        "stars": difficulty,
        "traits": clean(m.get("traits"), 60) or "Your toughest customer",
        "tagline": clean(m.get("tagline"), 90) or "Built from your description",
        "bio": clean(m.get("bio"), 320),
        "color": random.choice(COLORS),
        "voice": {"polly": random.choice(VOICES[gender]), "gender": gender, "pitch": 1.0, "rate": 1.0},
        "buyer": {
            "name": name,
            "title": clean(b.get("title"), 80) or "Buyer",
            "company": clean(b.get("company"), 100),
            "personality": clean(b.get("personality"), 400) or "Guarded and busy. Needs a real reason to keep talking.",
            "voice_style": clean(b.get("voice_style"), 200) or "Short, direct sentences.",
        },
        "rules": clean(m.get("rules"), 600) or "Be a realistic, skeptical buyer. Only warm up to good questions and real value.",
        "you_are_selling": sell,
        "you_are": "a sales rep selling " + sell[:120].rstrip("."),
        "call_type": call_type,
        "goal": "Book a next meeting at a specific time.",
        "pickup": "Hi... can I help you?" if call_type == "door" else "Hello?",
        "opening_line": clean(m.get("first_reaction"), 200) or "Okay... who is this?",
        "hidden_pains": three("hidden_pains", TEMPLATE_PAINS),
        "objections": three("objections", TEMPLATE_OBJECTIONS),
        "win_condition": f"{first} agrees to a next meeting at a specific time.",
        "close_condition": f"{first} agrees to buy today.",
        "upsell": {"offer": clean(upsell, 160) or "A bigger package or more seats.",
                   "keywords": ["upgrade", "bigger", "more seats", "premium", "whole team", "add on", "package"]},
        "deal_value": {"close": 10000, "upsell": 5000},
        "max_discount_pct": 10,
        "demo_lines": three("demo_lines", ["Okay.", "Hm. Go on.", "I don't know about that.", "Why does that matter?"]) + ["Mm-hm."],
        "category": "custom",
    }
    c.update(TUNING[difficulty])
    return c


def ai_buyer(sell, customer, difficulty, call_type):
    system = """You design realistic buyers for a sales practice game. The user tells you what they sell and
describes their toughest customer. Turn that into one specific, believable person. Keep it realistic for
their industry. Give them a creative alliterative nickname like "Budget Ben" or "Doorbell-Cam Doug".
Reply with ONLY this JSON:
{
  "nickname": "Alliterative Nickname",
  "gender": "male" or "female",
  "traits": "2-4 words, like 'Skeptical, rushed'",
  "tagline": "one punchy line about them",
  "bio": "1-2 sentences about who they are and why they're hard to sell to",
  "buyer": {"name": "First Last", "title": "job title", "company": "company or situation",
            "personality": "2-3 sentences on how they act on a sales call",
            "voice_style": "how they talk, with a couple of phrases they'd say"},
  "rules": "2-3 sentences of acting rules: what makes them warm up, what makes them shut down",
  "first_reaction": "what they say right after the rep introduces themselves",
  "hidden_pains": ["3 real problems they have, in their own words, that they only admit if asked well"],
  "objections": ["3 objections in their own words, easiest to hardest"],
  "upsell": {"offer": "a bigger deal they might go for"},
  "demo_lines": ["4 short things they'd say while listening"]
}"""
    door = " The rep is knocking on their door in person." if call_type == "door" else ""
    prompt = f"""WHAT I SELL: {sell}
MY TOUGHEST CUSTOMER: {customer}
DIFFICULTY: {difficulty} out of 5.{door}"""
    out = llm.ask_for_json(system, [{"role": "user", "content": prompt}], max_tokens=1200)
    if not isinstance(out, dict) or not out.get("objections"):
        return None
    return out


TEMPLATE_PAINS = [
    "Honestly, what we do now eats up a lot of time and nobody's happy with it.",
    "We tried something like this before and it went badly, so I'm gun-shy.",
    "My boss wants this fixed by the end of the quarter and I don't have a plan yet.",
]
TEMPLATE_OBJECTIONS = [
    "We already have something that works fine.",
    "How much is this going to cost me? Because we don't have budget.",
    "Just send me an email and I'll look at it.",
]


def template_buyer(sell, customer, difficulty):
    gender = random.choice(["male", "female"])
    first = random.choice(FIRST[gender])
    desc = customer.rstrip(".")
    title, company = guess_title(customer)
    adj = {1: "Friendly", 2: "Guarded", 3: "Skeptical", 4: "Tough", 5: "Brutal"}[difficulty]
    return {
        "nickname": f"{adj} {first}",
        "gender": gender,
        "traits": {1: "Open, curious", 2: "Polite, careful", 3: "Doubtful, busy", 4: "Blunt, price-focused", 5: "Cold, impatient"}[difficulty],
        "tagline": (desc[:80] + "...") if len(desc) > 80 else desc,
        "bio": f"{first} is the customer you described: {desc[:220]}.",
        "buyer": {"name": f"{first} {random.choice(LAST)}", "title": title, "company": company,
                  "personality": f"Acts exactly like this: {desc[:300]}.",
                  "voice_style": "Short and to the point."},
        "rules": f"You are this customer: {desc[:300]}. Stay in character. Warm up only to good questions and real value.",
        "first_reaction": "Okay... what's this about?",
    }


def guess_title(customer):
    # "A CFO at a 300-person construction company who hates software" -> ("CFO", "a 300-person construction company")
    head = re.split(r"\b(?:who|that|and|but)\b|[,;.]", customer, maxsplit=1, flags=re.I)[0].strip()
    head = re.sub(r"^(a|an|the|my)\s+", "", head, flags=re.I)
    title, company = head, ""
    for joiner in (" at ", " of ", " from ", " for "):
        if joiner in head.lower():
            i = head.lower().index(joiner)
            title, company = head[:i], head[i + len(joiner):]
            break
    title = title.strip()[:60]
    if not title or title.lower() in ("someone", "somebody", "person", "a person", "customer", "guy", "lady", "people"):
        title = "Prospect"
    return title[0].upper() + title[1:], company.strip()[:80]
