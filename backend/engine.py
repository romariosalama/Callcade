"""
The call engine. Runs one practice call between the rep (the player) and a buyer.

Each buyer has hidden state the player can't see:
  - mood (0-100): goes up when you sell well, down when you don't
  - hidden pains: problems they only admit if you ask good questions
  - objections: pushback they'll hit you with

To win you have to earn it. You can't book the meeting until you've turned
around enough objections, uncovered a pain, and the buyer's mood is high
enough. Closing on the spot needs even more. The server checks all of this,
so the AI can't just say yes because the player asked nicely.
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import db
import demo
import llm

DATA = Path(__file__).parent / "data"

CATEGORIES = {}
CHARACTERS = {}
# every file in data/ that has "characters" in it is an industry
industries = []
for path in DATA.glob("*.json"):
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "characters" in data:
        industries.append(data)
for cat in sorted(industries, key=lambda cat: cat["order"]):
    CATEGORIES[cat["id"]] = cat
    for c in cat["characters"]:
        c["category"] = cat["id"]
        CHARACTERS[c["id"]] = c

# how real buyers act, by industry (see data/realism.json)
REALISM = json.loads((DATA / "realism.json").read_text())

WON = ("closed", "meeting_booked")

# harder buyers warm up slower
MAX_GAIN = {1: 10, 2: 9, 3: 8, 4: 7, 5: 6}


def category_of(c):
    # custom buyers don't have a real industry, so they get a made-up one
    if c["category"] in CATEGORIES:
        return CATEGORIES[c["category"]]
    return {"id": "custom", "name": "Your buyer", "you_are": c.get("you_are", "a sales rep"),
            "call_type": c.get("call_type", "phone"), "blurb": ""}


def find_character(character_id):
    if character_id in CHARACTERS:
        return CHARACTERS[character_id]
    if str(character_id).startswith("custom-"):
        return db.get_custom_buyer(character_id)
    return None


def pickup_line(c):
    # real calls start with "Hello?", not a whole speech.
    # on an inbound call the customer called YOU, so they open with why they're calling
    if c.get("inbound"):
        return c["opening_line"]
    if c.get("pickup"):
        return c["pickup"]
    return "Hi... can I help you?" if category_of(c).get("call_type") == "door" else "Hello?"


def max_gain(c):
    return 5 if c.get("boss") else MAX_GAIN[c["stars"]]


def close_threshold(c):
    # buying on the spot takes way more trust than agreeing to a meeting
    return min(95, c["meeting_threshold"] + 20)


@dataclass
class Turn:
    speaker: str  # "rep" or "buyer"
    text: str
    mood: int  # buyer's mood after this turn
    note: str = ""  # buyer's private reaction (shown after the call)
    points: int = 0
    combo: int = 0
    objection: int | None = None  # objection the buyer raised this turn


@dataclass
class Call:
    id: str
    character: dict
    mood: int
    user_id: int | None = None
    turns: list = field(default_factory=list)
    pains_revealed: set = field(default_factory=set)
    objections_raised: set = field(default_factory=set)
    objections_handled: set = field(default_factory=set)
    pending_objection: int | None = None  # the objection the rep needs to answer right now
    status: str = "live"  # live, closed, meeting_booked, follow_up, hung_up, ended
    upsold: bool = False
    points: int = 0
    combo: int = 0
    best_combo: int = 0
    lowest_mood: int = 100
    saved: bool = False
    kind: str = "call"  # call, daily, challenge, or custom
    extra: str = ""     # the date for daily calls, the code for challenges, the name for custom buyers
    started_at: float = field(default_factory=time.time)

    @property
    def rep_turns(self):
        return sum(1 for t in self.turns if t.speaker == "rep")

    def next_objection(self):
        # the first objection the buyer hasn't used yet
        for i in range(len(self.character["objections"])):
            if i not in self.objections_raised:
                return i
        return None


# active calls are kept in memory AND in the database, so a restart doesn't lose them
CALLS = {}


def to_dict(call):
    return {
        "id": call.id, "character_id": call.character["id"], "mood": call.mood, "user_id": call.user_id,
        "turns": [t.__dict__ for t in call.turns],
        "pains_revealed": list(call.pains_revealed), "objections_raised": list(call.objections_raised),
        "objections_handled": list(call.objections_handled), "pending_objection": call.pending_objection,
        "status": call.status, "upsold": call.upsold, "points": call.points, "combo": call.combo,
        "best_combo": call.best_combo, "lowest_mood": call.lowest_mood, "saved": call.saved,
        "kind": call.kind, "extra": call.extra, "started_at": call.started_at,
    }


def from_dict(d):
    call = Call(id=d["id"], character=find_character(d["character_id"]), mood=d["mood"], user_id=d["user_id"])
    call.turns = [Turn(**t) for t in d["turns"]]
    call.pains_revealed = set(d["pains_revealed"])
    call.objections_raised = set(d["objections_raised"])
    call.objections_handled = set(d["objections_handled"])
    for key in ("pending_objection", "status", "upsold", "points", "combo", "best_combo", "lowest_mood",
                "saved", "kind", "extra", "started_at"):
        setattr(call, key, d[key])
    return call


def save(call):
    CALLS[call.id] = call
    db.save_active_call(call.id, call.user_id, to_dict(call))


def get(call_id):
    if call_id in CALLS:
        return CALLS[call_id]
    data = db.load_active_call(call_id)
    if not data or not find_character(data["character_id"]):
        return None
    call = from_dict(data)
    CALLS[call.id] = call
    return call


def forget(call):
    CALLS.pop(call.id, None)
    db.delete_active_call(call.id)


def start_call(character_id, user_id=None, kind="call", extra=""):
    c = find_character(character_id)
    if user_id:
        # one call at a time per person, so nobody holds a bunch of calls open
        for old_id in db.delete_user_active_calls(user_id):
            CALLS.pop(old_id, None)
    call = Call(id=uuid.uuid4().hex[:12], character=c, mood=c["starting_mood"],
                user_id=user_id, lowest_mood=c["starting_mood"], kind=kind, extra=extra)
    call.turns.append(Turn("buyer", pickup_line(c), call.mood))
    save(call)
    return call


def can_book(call, slack=0):
    # slack: if the buyer already said yes out loud and the rep did the work, a mood a few points
    # under the line still counts. real people don't say yes and then take it back
    c = call.character
    return (len(call.objections_handled) >= c["objections_to_win"]
            and len(call.pains_revealed) >= 1
            and call.mood >= c["meeting_threshold"] - slack)


def can_close(call):
    c = call.character
    return (len(call.objections_handled) >= c["objections_to_win"]
            and len(call.pains_revealed) >= 2
            and call.mood >= close_threshold(c))


def to_int(x, default=None):
    # small AI models sometimes send numbers as text like "5" or "+5"
    try:
        return int(float(str(x).strip()))
    except (TypeError, ValueError):
        return default


def simplify(x):
    return "".join(ch for ch in str(x).lower() if ch.isalnum())


def is_echo(call, rep_text, result):
    # the AI just repeated the rep's line, or its own last line
    reply = simplify(result.get("reply", ""))
    if not reply:
        return True
    last_buyer = next((t.text for t in reversed(call.turns[:-1]) if t.speaker == "buyer"), "")
    return reply == simplify(rep_text) or reply == simplify(last_buyer)


def rep_says(call, text):
    # the rep said something, the buyer reacts. returns the buyer's turn
    if call.status != "live":
        raise ValueError("This call is already over.")
    text = text.strip()[:600]
    if not text:
        raise ValueError("Say something first.")

    c = call.character
    call.turns.append(Turn("rep", text, call.mood))

    if llm.ai_on():
        result = ask_ai_buyer(call)
        if is_echo(call, text, result):
            result = ask_ai_buyer(call)  # smaller models sometimes parrot a line back. ask once more
            if is_echo(call, text, result):
                result["reply"] = demo.fresh_line(call, c.get("real_talk") or c["demo_lines"])
    else:
        result = demo.buyer_turn(call, text)

    # update the hidden state. the AI grades the line (great ... terrible) and WE turn that into
    # points, because models are much better at judging than at picking fair numbers
    rating = str(result.get("rating", "")).lower().strip()
    if rating in RATING_NAMES:
        change = rating_change(c, rating)
    else:
        change = to_int(result.get("mood_change"), 0)
    change = max(-25, min(max_gain(c), change))
    outcome_hint = str(result.get("outcome", "continue")).lower().strip()
    new_mood = max(0, min(100, call.mood + change))
    # grace period: nobody should get hung up on for a normal opener
    if call.rep_turns <= 2 and rating != "terrible" and change > -15:
        new_mood = max(new_mood, min(call.mood, c["hang_up_below"] + 3))
        if outcome_hint == "hung_up":
            result["outcome"] = "continue"
    call.mood = new_mood
    call.lowest_mood = min(call.lowest_mood, call.mood)

    # did they turn around the objection from last turn?
    handled_now = bool(result.get("objection_handled")) or (
        call.pending_objection is not None and (rating in ("great", "good") or (not rating and change > 0)))
    if handled_now:
        target = call.pending_objection
        if target is None:  # the buyer pushed back in their own words without naming which objection
            target = next((i for i in sorted(call.objections_raised) if i not in call.objections_handled), None)
        if target is None:
            target = call.next_objection()
        if target is not None:
            call.objections_raised.add(target)
            call.objections_handled.add(target)
    call.pending_objection = None

    pains = result.get("pains_revealed") or []
    if not isinstance(pains, list):
        pains = [pains]
    for i in pains:
        i = to_int(i)
        if i is not None and 0 <= i < len(c["hidden_pains"]):
            call.pains_revealed.add(i)

    obj = to_int(result.get("objection_raised"))
    if obj is not None and not 0 <= obj < len(c["objections"]):
        obj = None

    reply = str(result.get("reply") or "...").strip()
    outcome = str(result.get("outcome", "continue")).lower().strip()

    # the server has the final say on how the call ends
    if outcome == "hung_up" or call.mood <= c["hang_up_below"]:
        call.status = "hung_up"
        if outcome != "hung_up":
            reply = "Look, I'm not interested. I've gotta go."
        obj = None
    elif outcome == "closed" and can_close(call):
        call.status = "closed"
        call.upsold = bool(result.get("upsell"))
    elif outcome in WON and can_book(call, slack=8):
        call.mood = max(call.mood, c["meeting_threshold"])  # they said yes out loud, so it counts
        if outcome == "closed":
            reply = "Whoa, I'm not buying anything today. But okay, I'll give you a meeting. Send me an invite."
        call.status = "meeting_booked"
    elif outcome in WON:
        # they asked too early, so the buyer pushes back instead
        obj = call.next_objection()
        if obj is not None:
            reply = c["objections"][obj]
        else:
            reply = "I'm not there yet. You still haven't really convinced me."
    elif call.rep_turns >= c["max_turns"]:
        call.status = "ended"
        reply += " Sorry, I've got to jump. Something just came up."

    if obj is not None:
        call.objections_raised.add(obj)
        call.pending_objection = obj

    # points and combos
    points = 0
    if change > 0:
        call.combo += 1
        points = change * call.combo
    else:
        call.combo = 0
    call.best_combo = max(call.best_combo, call.combo)
    call.points += points

    why = str(result.get("why", "")).strip() or RATING_NOTES.get(rating, "")
    turn = Turn("buyer", reply, call.mood, why, points, call.combo, obj)
    call.turns.append(turn)
    save(call)
    return turn


WARM_LEAD_MOOD = 45


def end_call(call):
    # the call is over with no deal. did we at least leave them warm?
    if call.status in ("live", "ended"):
        if call.mood >= WARM_LEAD_MOOD and call.rep_turns >= 3:
            call.status = "follow_up"
        else:
            call.status = "ended"


# ---------------- AI buyer ----------------

RATING_NAMES = ("great", "good", "okay", "weak", "bad", "terrible")
RATING_NOTES = {
    "great": "That's exactly what a top rep would say here.",
    "good": "Solid line. It moved things forward.",
    "okay": "Fine, but generic. Make it about them.",
    "weak": "That felt salesy or vague. Ask about their situation instead.",
    "bad": "That pushed them away: too pushy, too long, or dodging.",
    "terrible": "That burned trust. Pressure, arguing or rudeness ends calls.",
}


def rating_change(c, rating):
    return {"great": max_gain(c), "good": strong_line_value(c), "okay": 2, "weak": -4, "bad": -10, "terrible": -20}[rating]


def strong_line_value(c):
    # how much a "good" line is worth, so a good rep can book the meeting in about 6 strong turns
    gap = c["meeting_threshold"] - c["starting_mood"]
    return max(4, min(max_gain(c), round(gap / 6)))


def buyer_prompt(call):
    c = call.character
    b = c["buyer"]
    cat = category_of(c)
    door = cat.get("call_type") == "door"

    pains = "".join(f"[{i}] {p}{' (already revealed)' if i in call.pains_revealed else ''}\n"
                    for i, p in enumerate(c["hidden_pains"]))
    objections = "".join(f"[{i}] {o}{' (already raised)' if i in call.objections_raised else ''}\n"
                         for i, o in enumerate(c["objections"]))

    handled = len(call.objections_handled)
    need = c["objections_to_win"]
    if handled < need:
        gate = (f"The rep has turned around {handled} of the {need} objections you need good answers to. "
                "You are NOT ready to agree to anything. If they ask for a meeting or the sale, push back with an objection.")
    elif not call.pains_revealed:
        gate = "You haven't shared a real problem yet, so you don't see why you'd meet. Don't agree yet."
    else:
        gate = "The rep has earned the right to ask. Agree if your mood is high enough and they actually ask."

    if door:
        setting = (f"IN PERSON at your front door. Someone knocked; you opened and said \"{pickup_line(c)}\" "
                   "You don't know who they are yet. 'hung_up' = you close the door.")
    elif c.get("inbound"):
        setting = (f"A PHONE CALL YOU made to the dealership. The salesperson answered; you opened with \"{pickup_line(c)}\" "
                   "'hung_up' = you hang up and call another dealer.")
    else:
        setting = (f"A PHONE CALL. You picked up and said \"{pickup_line(c)}\" You don't know who's calling until they "
                   "tell you. 'hung_up' = you hang up.")
    if not c.get("inbound"):
        setting += (f" Once they say who they are, your first reaction is like: \"{c['opening_line']}\" (in your own words). "
                    "If they never say who they are, ask. If they open with a long pitch, cut them off.")
    if c.get("context"):
        setting += " Situation: " + c["context"]

    talk = " ".join(f"\"{x}\"" for x in c.get("real_talk", []))

    return f"""Role-play a real buyer so a salesperson can practice. Stay in character. Never mention being an AI or a practice tool.

THE CALL: {setting}
The rep is {cat['you_are']}.

YOU: {b['name']}, {b['title']} ({b['company']}). {b['personality']}
How you talk: {b['voice_style']} {("Examples: " + talk) if talk else ""}
Your rules: {c['rules']}
{("Wins you over: " + "; ".join(c["wins"]) + ".") if c.get("wins") else ""}
{("Shuts you down: " + "; ".join(c["turn_offs"]) + ".") if c.get("turn_offs") else ""}

THEY'RE SELLING (you only know what they tell you): {c['you_are_selling']}
Bigger deal they might offer: {c['upsell']['offer']}

HIDDEN PAINS. Reveal one at a time, only when earned by a good open question or real understanding. Never list them:
{pains}
OBJECTIONS. Raise them naturally. One only goes away when the rep acknowledges it, asks about it, and answers with
something that matters to you. Repeating the pitch doesn't count:
{objections}
MOOD: {call.mood}/100. Under 30 short and cold, 30-60 guarded, over 60 open. At {c['hang_up_below']} or lower you end it.
RATE THE REP'S LAST LINE honestly (be fair: a good rep must be able to win you over in about 8 to 12 turns):
- "great": what a top rep would say here. Specific to you, uses what you said, honest proof, or handles your pushback well.
- "good": solid. A real question about your situation, calm, moves things forward.
- "okay": fine but generic.
- "weak": salesy, vague, a bit long (over ~{c['patience_words']} words), or ignores what you just said.
- "bad": a pitch dump, buzzwords, dodging your question, pushy, instant discount.
- "terrible": rude, lying, fake urgency, arguing with you.
Your mood follows the rating, so let your tone match it: warmer after great/good, colder after weak/bad.
Never repeat your previous line or the rep's line back. If you agree to a meeting in your reply, outcome MUST be "meeting_booked".
WHERE THINGS STAND: {gate}

ENDINGS
- "meeting_booked": only if {c['win_condition']} Mood at least {c['meeting_threshold']}.
- "closed": only if {c['close_condition']} Mood at least {close_threshold(c)} AND they asked for the sale. Rare.
  "upsell": true only if they offered the bigger deal and it fits you.
- "hung_up": they lost you. Otherwise "continue".

{realism_block(c, cat)}

TALK LIKE A REAL PERSON: your words are read aloud. Usually ONE short sentence, under 20 words. Two or three only when
you're opening up. Contractions, the odd "uh", "yeah", "I mean". No lists, emojis, stage directions or asterisks.

Reply with ONLY this JSON:
{{"rating": "great" | "good" | "okay" | "weak" | "bad" | "terrible",
 "reply": "what you say out loud",
 "why": "one short coaching sentence for the rep about their last line",
 "objection_handled": true if their last line properly handled the pushback you gave in your previous reply, else false,
 "pains_revealed": [pain numbers revealed in THIS reply],
 "objection_raised": number of the objection you push back with in THIS reply (even in different words), or null,
 "outcome": "continue" | "meeting_booked" | "closed" | "hung_up", "upsell": true | false}}"""


def realism_block(c, cat):
    # how real buyers act (data/realism.json), plus real lines and an example call from their industry
    out = ["HOW REAL BUYERS ACT (from real call research, follow closely):"]
    out += ["- " + line for line in REALISM["global"]["rules"]]
    pack = REALISM["industries"].get(cat["id"])
    if pack:
        out.append("Real things people in this industry say: " + " ".join(f"\"{x}\"" for x in pack["real_lines"]))
        out.append("EXAMPLE of a real call in this industry (other people; for rhythm only, don't copy):")
        out += [("  Buyer: " if who == "buyer" else "  Rep: ") + text for who, text in pack["example"]]
    return "\n".join(out)


def ask_ai_buyer(call):
    messages = []
    for t in call.turns:
        if t.speaker == "buyer":
            messages.append({"role": "assistant", "content": json.dumps({"reply": t.text})})
        else:
            messages.append({"role": "user", "content": t.text})
    # the APIs want the conversation to start with the user, so the ring goes first
    first = "*knocks on the door*" if category_of(call.character).get("call_type") == "door" else "*phone rings*"
    messages.insert(0, {"role": "user", "content": first})
    return llm.ask_for_json(buyer_prompt(call), messages, max_tokens=400)
