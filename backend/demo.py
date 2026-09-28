"""
Demo mode: a simple rule-based buyer so the app works with no AI connected.

It just looks for good and bad sales habits (open questions, listening, long
pitches, buzzwords, pressure, discounts) and reacts. The real AI buyer is way
more natural, but this is good enough for building and testing.
"""

import random
import re

OPEN_QUESTION = re.compile(
    r"\b(what|how|why|walk me through|tell me|help me understand|describe|can you share)\b", re.I
)
EMPATHY = ["makes sense", "i understand", "that's fair", "totally get", "i hear you", "i get it",
           "sounds like", "what i'm hearing", "that must", "fair enough", "good question", "fair question",
           "totally fair", "you're right", "i'm sorry"]
BUZZWORDS = ["synergy", "revolutionary", "game-changing", "game changer", "best-in-class",
             "cutting-edge", "cutting edge", "disrupt", "paradigm", "world-class", "leverage"]
PRESSURE = ["sign today", "sign right now", "buy right now", "decide right now", "limited time", "act fast",
            "today only", "before it's gone", "offer expires", "last chance"]
RUDE = ["stupid", "shut up", "dumb", "idiot", "whatever"]
NEXT_STEP = re.compile(
    r"\b(meeting|calendar|schedule|demo|next week|tomorrow|monday|tuesday|wednesday|thursday|friday|"
    r"\d+ minutes|book a|set up a (time|call)|follow[- ]up call|invite|deep[- ]dive|audit)\b", re.I
)
ASK_FOR_SALE = re.compile(
    r"\b(sign up|get you started|get started|move forward|ready to buy|start today|send (over )?the contract|"
    r"credit card|card number|buy it|purchase|"
    r"go ahead with|want to buy|shall we start|ready to start|onboard you)\b", re.I
)
BIG_DISCOUNT = re.compile(r"\b([2-9]\d|100)\s*(%|percent)", re.I)

# How much a good line helps (GAIN) and a bad line hurts (PAIN), by star rating.
GAIN = {1: 1.0, 2: 0.9, 3: 0.8, 4: 0.7, 5: 0.6, 6: 0.5}
PAIN = {1: 0.6, 2: 0.8, 3: 1.0, 4: 1.2, 5: 1.4, 6: 1.6}


def buyer_turn(call, text):
    c = call.character
    lower = text.lower()
    words = len(text.split())
    change, why = 0, []
    reply = None
    pains_revealed, objection = [], None

    # stuff that doesn't make sense as a sales line ("yes", "what", random words)
    words_only = re.sub(r"[^a-z' ]", "", lower).split()
    greeting = any(g in lower for g in ["hi", "hey", "hello", "good morning", "good afternoon"])
    if len(words_only) <= 2 and not greeting:
        confused = ["Sorry, what?", "...What do you mean?", "I'm sorry, who is this?", "Uh, okay?"]
        return {"reply": fresh_line(call, confused), "mood_change": -4,
                "why": "That didn't make sense to them. Every line should have a point.", "outcome": "continue"}

    introduced = re.search(r"\b(this is|my name|i'm|i am|calling from|with |from )", lower)
    if call.rep_turns == 1 and not introduced and not c.get("inbound"):
        change -= 3
        why.append("You never said who you are. Always introduce yourself first.")

    if any(w in lower for w in RUDE):
        return {"reply": "Wow. Okay, we're done here.", "mood_change": -25,
                "why": "Rudeness ends calls instantly.", "outcome": "hung_up"}

    patience = c["patience_words"]
    if words > patience:
        change -= 10 if words < patience * 2 else 18
        why.append(f"That was {words} words. {c['buyer']['name'].split()[0]} tunes out after about {patience}.")
    if any(w in lower for w in BUZZWORDS):
        change -= 8
        why.append("Buzzwords make you sound like every other cold caller.")
    if any(w in lower for w in PRESSURE):
        change -= 12
        why.append("Pressure tactics kill trust.")
    if BIG_DISCOUNT.search(text) and ("off" in lower or "discount" in lower):
        change -= 10
        why.append("A big discount with nothing in return tells them your price was fake.")
    heard = any(w in lower for w in EMPATHY)
    if heard:
        change += 4
        why.append("You acknowledged what they said. Buyers notice that.")

    is_question = "?" in text
    is_open = is_question and OPEN_QUESTION.search(text)
    mood_after = call.mood + change
    upsell = any(k in lower for k in c["upsell"]["keywords"])
    answering = call.pending_objection is not None

    # they just gave you an objection. did you actually deal with it?
    if answering and not heard and not is_question:
        change -= 5
        why.append("You talked right past their objection. Acknowledge it and ask about it first.")
    elif answering and heard and is_question:
        change += 3
        why.append("Nice objection handling: you acknowledged it and asked a question.")

    # asking for the sale on the spot
    if ASK_FOR_SALE.search(text) and is_question:
        need = min(95, c["meeting_threshold"] + 20)
        if mood_after + 5 >= need:
            return {"reply": "...You know what? Let's do it." + (" And yeah, let's do the bigger deal." if upsell else ""),
                    "mood_change": change + 5, "why": "You built enough trust to ask for the sale, and you asked.",
                    "outcome": "closed", "upsell": upsell}
        change -= 4
        why.append("You asked for the sale before they were ready. Earn trust first, or ask for a smaller step.")
        objection = call.next_objection()
        reply = c["objections"][objection] if objection is not None else "Whoa, slow down."

    # asking for a meeting / next step
    elif NEXT_STEP.search(text) and is_question:
        if mood_after + 5 >= c["meeting_threshold"]:
            return {"reply": "...Okay. You've earned it. Send me the invite, and don't be late.",
                    "mood_change": change + 5, "why": "You earned trust first, then asked for a clear next step.",
                    "outcome": "meeting_booked"}
        change -= 3
        why.append("You asked for the meeting before earning it. Uncover a real pain first.")
        objection = call.next_objection()
        reply = c["objections"][objection] if objection is not None else "I'm not there yet."

    elif is_open:
        change += 5
        why.append("Good open-ended question; it got them talking.")
        remaining = [i for i in range(len(c["hidden_pains"])) if i not in call.pains_revealed]
        if remaining and mood_after + 8 >= c["pain_gate"]:
            pains_revealed = [remaining[0]]
            reply = c["hidden_pains"][remaining[0]]
        elif remaining:
            why.append("Good question, but they don't trust you enough yet to open up.")
    elif is_question:
        change += 2
        why.append("Closed yes/no question. Open-ended ones uncover more.")

    # the first thing they say back after you introduce yourself
    if reply is None and call.rep_turns == 1 and not c.get("inbound"):
        reply = c["opening_line"] if introduced else "Sorry, who is this?"

    # buyers push back a lot, so throw an objection if nothing else happened
    if reply is None and (call.rep_turns % 2 == 0 or not call.objections_raised):
        objection = call.next_objection()
        if objection is not None:
            reply = c["objections"][objection]

    if reply is None:
        reply = fresh_line(call, c["demo_lines"] + c.get("real_talk", []))

    if not why:
        why.append("Nothing moved the needle. Try a discovery question.")

    # people get impatient the longer a call goes
    if call.rep_turns > c["max_turns"] // 2:
        change -= 2
        why.append("The call is dragging on. Get to the point.")

    # harder characters warm up slower and punish mistakes harder
    stars = c["stars"] + (1 if c.get("boss") else 0)
    change = round(change * (GAIN[stars] if change > 0 else PAIN[stars]))

    return {"reply": reply, "mood_change": change, "why": " ".join(why),
            "pains_revealed": pains_revealed, "objection_raised": objection, "outcome": "continue"}


def fresh_line(call, lines):
    # don't say the same thing twice in a row
    said = [t.text for t in call.turns[-6:] if t.speaker == "buyer"]
    options = [line for line in lines if line not in said] or lines
    return random.choice(options)
