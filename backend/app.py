"""
Callcade web server.
Run it from the backend folder with:  uvicorn app:app --reload
then open http://localhost:8000
"""

import logging
import re
import secrets
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")  # has to run before the other modules read their settings

from fastapi import FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import account  # noqa: E402
import auth  # noqa: E402
import clutch  # noqa: E402
import custom  # noqa: E402
import daily  # noqa: E402
import db  # noqa: E402
import engine  # noqa: E402
import gauntlet  # noqa: E402
import llm  # noqa: E402
import mailer  # noqa: E402
import mistakes  # noqa: E402
import plans  # noqa: E402
import profiles  # noqa: E402
import ratelimit  # noqa: E402
import scoring  # noqa: E402
import voice  # noqa: E402

# log to the terminal and to a file, so when something breaks I can see why
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(Path(__file__).parent / "callcade.log")],
)
log = logging.getLogger("callcade")

app = FastAPI(title="Callcade")
app.include_router(auth.router)
app.include_router(account.router)
db.setup()

FRONTEND = Path(__file__).parent.parent / "frontend"


@app.exception_handler(Exception)
async def crash_handler(request: Request, exc: Exception):
    log.exception("Crash on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something broke on our end. Try again."})


# the only character fields the browser gets. pains, objections and rules stay secret
PUBLIC_FIELDS = ["id", "level", "nickname", "stars", "boss", "traits", "tagline", "bio", "color", "goal",
                 "custom", "you_are", "call_type", "inbound", "context",
                 "you_are_selling", "hang_up_below", "max_turns", "close_condition", "deal_value",
                 "max_discount_pct", "objections_to_win", "category"]


def public_character(c):
    out = {k: c.get(k) for k in PUBLIC_FIELDS}
    out["buyer"] = {k: c["buyer"][k] for k in ("name", "title", "company")}
    out["upsell"] = c["upsell"]["offer"]
    out["voice"] = {k: c["voice"].get(k) for k in ("gender", "pitch", "rate")}
    out["multiplier"] = scoring.BOSS_MULTIPLIER if c.get("boss") else scoring.MULTIPLIER[c["stars"]]
    return out


def require_admin(request):
    user = auth.require_user(request)
    if not user["is_admin"]:
        raise HTTPException(403, "Admins only.")
    return user


class StartCall(BaseModel):
    character_id: str


class Say(BaseModel):
    text: str


class SpeakRequest(BaseModel):
    text: str
    character_id: str = ""
    voice: str = ""  # used by the gauntlet, which doesn't have a character
    gender: str = ""
    mood: int | None = None  # the buyer sounds annoyed or warm depending on how the call is going


class StartGauntlet(BaseModel):
    category: str = "mixed"


class IndustryPick(BaseModel):
    category: str


class ProfileUpdate(BaseModel):
    display_name: str
    color: str
    bio: str = ""


class ResultRef(BaseModel):
    result_id: int


class Pick(BaseModel):
    index: int


class Classify(BaseModel):
    index: int
    type: str


class ClutchPick(BaseModel):
    choice: int | None = None  # None = ran out of time


class BuildBuyer(BaseModel):
    sell: str
    customer: str
    difficulty: int = 3
    call_type: str = "phone"


class NewPlan(BaseModel):
    plan: str


@app.get("/api/config")
def config():
    return {"mode": llm.MODE, "ai": llm.ai_on(), "server_voice": voice.ENABLED, "pro_price": plans.PRO_PRICE,
            "plans": plans.PLANS, "email_sending": mailer.enabled()}


@app.get("/api/categories")
def categories(request: Request):
    user = auth.current_user(request)
    results = db.user_results(user["id"]) if user else []
    unlocked = profiles.unlocked_ids(results)
    beaten = profiles.beaten_ids(results)
    best = profiles.best_scores(results)

    out = []
    for cat in engine.CATEGORIES.values():
        chars = []
        for c in sorted(cat["characters"], key=lambda c: c["level"]):
            pc = public_character(c)
            ok, reason = plans.access(user, c, unlocked)
            pc["unlocked"] = ok
            pc["lock"] = reason  # "", "locked", "signup" or "pro"
            pc["beaten"] = c["id"] in beaten
            pc["best"] = best.get(c["id"], 0)
            chars.append(pc)
        out.append({"id": cat["id"], "name": cat["name"], "blurb": cat["blurb"],
                    "you_are": cat["you_are"], "color": cat["color"], "labels": cat["labels"],
                    "call_type": cat.get("call_type", "phone"), "characters": chars})
    return out


@app.get("/api/plan")
def my_plan(request: Request):
    return plans.summary(auth.current_user(request))


@app.post("/api/plan/industry")
def pick_industry(req: IndustryPick, request: Request):
    user = auth.require_user(request)
    if plans.plan_of(user) != "free":
        raise HTTPException(400, "Pro already has every industry.")
    if req.category not in engine.CATEGORIES:
        raise HTTPException(400, "Unknown industry.")
    ok, _ = plans.can_switch_industry(user)
    if not ok:
        raise HTTPException(400, "You can switch your free industry once every 30 days.")
    db.set_free_category(user["id"], req.category)
    return plans.summary(db.get_user(user["id"]))


@app.post("/api/plan/upgrade")
def upgrade(request: Request):
    auth.require_user(request)
    # TODO: hook up Stripe Checkout here
    raise HTTPException(501, "Payments aren't set up yet. Pro is coming soon!")


# ---------------- calls ----------------

def get_call(call_id, request):
    call = engine.get(call_id)
    if not call:
        raise HTTPException(404, "Call not found. It may have timed out.")
    user = auth.current_user(request)
    if call.user_id is not None and (not user or user["id"] != call.user_id):
        raise HTTPException(403, "That's not your call.")
    return call


def call_started(call):
    return {"call_id": call.id, "buyer_says": call.turns[0].text, "mood": call.mood, "status": call.status,
            "character": public_character(call.character), "kind": call.kind}


def guest_call_limit(request):
    ratelimit.check("guestcall:" + ratelimit.client_ip(request), 10, 3600,
                    "That's a lot of guest calls. Make a free account to keep going.")


def new_best(user_id, mode, score):
    old = [r["points"] for r in db.user_results(user_id) if r["mode"] == mode]
    return score > max(old, default=0)


@app.post("/api/calls")
def start_call(req: StartCall, request: Request):
    c = engine.find_character(req.character_id)
    if not c:
        raise HTTPException(404, "Unknown buyer.")
    user = auth.current_user(request)
    unlocked = profiles.unlocked_ids(db.user_results(user["id"])) if user else set()
    # custom buyers aren't part of the level ladder, anyone with the link can call them
    ok, reason = (True, None) if c.get("custom") else plans.access(user, c, unlocked)
    if not ok:
        messages = {
            "signup": "Make a free account to play past level 1.",
            "pro": "This buyer is part of Callcade Pro.",
            "locked": "Beat the previous level to unlock this buyer.",
        }
        raise HTTPException(403, messages[reason])
    if user and plans.left_today(user, "call") == 0:
        raise HTTPException(429, "You've used all 10 free calls for today. Come back tomorrow or go Pro for unlimited calls.")
    if user:
        db.add_usage(user["id"], "call")
    else:
        guest_call_limit(request)
    call = engine.start_call(c["id"], user["id"] if user else None, kind="custom" if c.get("custom") else "call",
                             extra=c["nickname"] if c.get("custom") else "")
    return call_started(call)


@app.post("/api/calls/{call_id}/say")
def say(call_id: str, req: Say, request: Request):
    call = get_call(call_id, request)
    ratelimit.check("say:" + call_id, 20, 60, "You're talking really fast. Give the buyer a second.")
    try:
        turn = engine.rep_says(call, req.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # usually the AI not being set up
        log.warning("AI buyer failed: %s", e)
        call.turns.pop()  # undo the rep's line so they can try again
        raise HTTPException(502, f"The AI buyer couldn't respond: {e}")
    c = call.character
    return {
        "buyer_says": turn.text,
        "mood": call.mood,
        "status": call.status,
        "points_earned": turn.points,
        "combo": turn.combo,
        "call_points": call.points,
        "objection": turn.objection is not None,
        "handled": len(call.objections_handled),
        "need": c["objections_to_win"],
        "pains": len(call.pains_revealed),
        "note": turn.note,
    }


@app.post("/api/calls/{call_id}/end")
def end_call(call_id: str, request: Request):
    call = get_call(call_id, request)
    engine.end_call(call)
    card = scoring.scorecard(call)
    card["progress"] = None
    card["kind"] = call.kind
    card["result_id"] = None

    if call.user_id and not call.saved:
        p = card["points"]
        details = {b["label"]: round(100 * b["points"] / b["max"]) for b in card["score"]["breakdown"]}
        badges = [b["id"] for b in p["badges"] if b["points"] > 0]
        before = db.user_results(call.user_id)
        points_before = sum(r["points"] for r in before)

        if call.kind == "daily":
            already = any(r["mode"] == "daily" and r["extra"] == call.extra for r in before)
            if not already:
                card["result_id"] = db.save_result(call.user_id, "daily", call.character["category"], call.character["id"],
                                                   call.status, p["total"], card["score"]["total"], p["revenue"],
                                                   call.best_combo, badges, call.rep_turns, call.extra, details)
        elif call.kind == "custom":
            # saved for your history, but worth 0 points so nobody farms an easy buyer they built
            card["result_id"] = db.save_result(call.user_id, "custom", "custom", call.character["id"], call.status,
                                               0, card["score"]["total"], 0, call.best_combo, badges, call.rep_turns,
                                               call.extra, details)
        elif call.kind == "challenge":
            db.save_result(call.user_id, "challenge", call.character["category"], call.character["id"], call.status,
                           p["total"], card["score"]["total"], p["revenue"], call.best_combo, badges, call.rep_turns,
                           call.extra, details)
        else:
            unlocked_before = profiles.unlocked_ids(before)
            best_before = profiles.best_scores(before).get(call.character["id"], 0)
            card["result_id"] = db.save_result(call.user_id, "call", call.character["category"], call.character["id"],
                                               call.status, p["total"], card["score"]["total"], p["revenue"],
                                               call.best_combo, badges, call.rep_turns, "", details)
            after = db.user_results(call.user_id)
            user = db.get_user(call.user_id)
            new_ids = profiles.unlocked_ids(after) - unlocked_before
            card["progress"] = {
                "new_best": p["total"] > best_before,
                "unlocked": [public_character(engine.CHARACTERS[i]) for i in new_ids
                             if plans.access(user, engine.CHARACTERS[i], new_ids)[0]],
                "pro_next": [public_character(engine.CHARACTERS[i]) for i in new_ids
                             if plans.access(user, engine.CHARACTERS[i], new_ids)[1] == "pro"],
            }
        call.saved = True

        rank_before = profiles.rank_for(points_before)["name"]
        rank_after = profiles.rank_for(db.career_points(call.user_id))
        card["progress"] = card["progress"] or {"new_best": False, "unlocked": [], "pro_next": []}
        card["progress"]["rank"] = rank_after
        card["progress"]["rank_up"] = rank_after["name"] if rank_after["name"] != rank_before else None

    if call.kind == "challenge":
        ch = db.get_challenge(call.extra)
        if ch:
            card["challenge"] = {"code": ch["code"], "their_name": ch["display_name"], "their_points": ch["points"],
                                 "their_outcome": ch["outcome"], "your_points": card["points"]["total"],
                                 "won": card["points"]["total"] > ch["points"]}
    engine.forget(call)
    return card


# ---------------- build your own buyer ----------------

BUILDS_PER_DAY = {"free": 3, "pro": 25}


@app.post("/api/custom-buyers")
def build_buyer(req: BuildBuyer, request: Request):
    user = auth.current_user(request)
    if user:
        plan = plans.plan_of(user)
        limit = BUILDS_PER_DAY.get(plan, 3)
        if plans.used_today(user, "build") >= limit:
            extra = " Go Pro to build more." if plan == "free" else ""
            raise HTTPException(429, f"You've built {limit} buyers today.{extra}")
    else:
        ratelimit.check("build:" + ratelimit.client_ip(request), 2, 3600,
                        "Make a free account to build more buyers.")
    try:
        c = custom.build(req.sell, req.customer, req.difficulty, req.call_type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.save_custom_buyer(c["id"], user["id"] if user else None, c)
    if user:
        db.add_usage(user["id"], "build")
    log.info("Built custom buyer %s", c["id"])
    return public_character(c)


@app.get("/api/custom-buyers")
def my_buyers(request: Request):
    user = auth.current_user(request)
    if not user:
        return []
    return [public_character(c) for c in db.user_custom_buyers(user["id"])]


@app.get("/api/custom-buyers/{buyer_id}")
def one_buyer(buyer_id: str):
    c = db.get_custom_buyer(buyer_id) if buyer_id.startswith("custom-") else None
    if not c:
        raise HTTPException(404, "That buyer doesn't exist anymore.")
    return public_character(c)


@app.delete("/api/custom-buyers/{buyer_id}")
def delete_buyer(buyer_id: str, request: Request):
    user = auth.require_user(request)
    db.delete_custom_buyer(buyer_id, user["id"])
    return {"ok": True}


# ---------------- daily challenge ----------------

@app.get("/api/daily")
def daily_info(request: Request):
    user = auth.current_user(request)
    day = daily.today()
    c = daily.pick(day)
    played = None
    if user:
        mine = [r for r in db.user_results(user["id"]) if r["mode"] == "daily" and r["extra"] == day]
        if mine:
            played = {"points": mine[0]["points"], "outcome": mine[0]["outcome"]}
    top = db.leaderboard(mode="daily", extra=day, limit=10, verified_only=mailer.enabled())
    return {"date": day, "character": public_character(c), "category": engine.CATEGORIES[c["category"]]["name"],
            "played": played,
            "top": [{"username": r["username"], "display_name": r["display_name"], "color": r["color"],
                     "score": r["score"]} for r in top]}


@app.post("/api/daily/start")
def daily_start(request: Request):
    user = auth.current_user(request)
    day = daily.today()
    if user and any(r["mode"] == "daily" and r["extra"] == day for r in db.user_results(user["id"])):
        raise HTTPException(400, "You already played today's challenge. A new buyer drops at midnight (Pacific).")
    if not user:
        guest_call_limit(request)
    call = engine.start_call(daily.pick(day)["id"], user["id"] if user else None, kind="daily", extra=day)
    return call_started(call)


# ---------------- challenge a friend ----------------

@app.post("/api/challenges")
def make_challenge(req: ResultRef, request: Request):
    user = auth.require_user(request)
    r = db.get_result(req.result_id)
    if not r or r["user_id"] != user["id"] or r["mode"] not in ("call", "daily"):
        raise HTTPException(400, "You can only challenge people with one of your own calls.")
    existing = db.challenge_for_result(r["id"])
    if existing:
        return {"code": existing["code"]}
    code = secrets.token_urlsafe(6)
    db.create_challenge(code, user["id"], r["id"], r["character_id"], r["points"], r["outcome"])
    return {"code": code}


@app.get("/api/challenges/{code}")
def get_challenge(code: str):
    ch = db.get_challenge(code)
    if not ch:
        raise HTTPException(404, "That challenge doesn't exist.")
    c = engine.CHARACTERS[ch["character_id"]]
    return {"code": code, "from": {"username": ch["username"], "display_name": ch["display_name"], "color": ch["color"]},
            "points": ch["points"], "outcome": ch["outcome"], "character": public_character(c),
            "category": engine.CATEGORIES[c["category"]]["name"]}


@app.post("/api/challenges/{code}/start")
def start_challenge(code: str, request: Request):
    ch = db.get_challenge(code)
    if not ch:
        raise HTTPException(404, "That challenge doesn't exist.")
    user = auth.current_user(request)
    if user and plans.left_today(user, "call") == 0:
        raise HTTPException(429, "You're out of free calls for today.")
    if user:
        db.add_usage(user["id"], "call")
    else:
        guest_call_limit(request)
    call = engine.start_call(ch["character_id"], user["id"] if user else None, kind="challenge", extra=code)
    return call_started(call)


# ---------------- voice ----------------

ALL_VOICES = {c["voice"]["polly"] for c in engine.CHARACTERS.values()}


@app.post("/api/voice")
def speak(req: SpeakRequest, request: Request):
    ratelimit.check("voice:" + ratelimit.client_ip(request), 60, 60)
    if not req.text.strip():
        raise HTTPException(400, "Bad request.")
    c = engine.find_character(req.character_id) if req.character_id else None
    if c:
        v = c["voice"]
    elif req.voice in ALL_VOICES:  # the gauntlet picks a voice by name
        v = {"polly": req.voice, "gender": "female" if req.gender == "female" else "male"}
    else:
        raise HTTPException(400, "Bad request.")
    out = voice.speak(req.text[:600], v, req.mood)
    if not out:
        return Response(status_code=204)  # the browser will use its own voice
    audio, mime = out
    return Response(content=audio, media_type=mime)


# ---------------- objection gauntlet ----------------

GAUNTLET_CATEGORIES = ["mixed", "general"] + list(engine.CATEGORIES)


def get_run(runs, run_id, request):
    run = runs.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found.")
    user = auth.current_user(request)
    if run["user_id"] is not None and (not user or user["id"] != run["user_id"]):
        raise HTTPException(403, "That's not your run.")
    return run


@app.post("/api/gauntlet")
def start_gauntlet(req: StartGauntlet, request: Request):
    if req.category not in GAUNTLET_CATEGORIES:
        raise HTTPException(400, "Unknown category.")
    user = auth.current_user(request)
    if not user:
        raise HTTPException(401, "Make a free account to play the Objection Gauntlet.")
    if plans.left_today(user, "gauntlet") == 0:
        raise HTTPException(429, "You've used your 3 free gauntlet runs for today. Go Pro for unlimited runs.")
    db.add_usage(user["id"], "gauntlet")
    run = gauntlet.start(req.category, user["id"])
    return {"run_id": run["id"], "round": gauntlet.current_round(run)}


@app.post("/api/gauntlet/{run_id}/ready")
def gauntlet_ready(run_id: str, request: Request):
    # the clock only starts once the objection is actually on screen
    run = get_run(gauntlet.RUNS, run_id, request)
    if run["done"]:
        raise HTTPException(400, "This run is over.")
    run["round_started"] = time.time()
    return gauntlet.current_round(run)


@app.post("/api/gauntlet/{run_id}/answer")
def gauntlet_answer(run_id: str, req: Say, request: Request):
    run = get_run(gauntlet.RUNS, run_id, request)
    try:
        result = gauntlet.answer(run, req.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.warning("Gauntlet grading failed: %s", e)
        raise HTTPException(502, f"Grading failed: {e}")

    out = {"result": result, "total": run["total"]}
    if run["done"]:
        summary = gauntlet.summary(run)
        summary["new_best"] = False
        if run["user_id"] and not run["saved"]:
            summary["new_best"] = new_best(run["user_id"], "gauntlet", run["total"])
            db.save_result(run["user_id"], "gauntlet", run["category"], "", "completed", run["total"],
                           round(summary["avg_score"] * 10), best_combo=run["best_streak"], turns=len(run["answers"]))
            run["saved"] = True
        out["summary"] = summary
    else:
        out["next"] = gauntlet.current_round(run)
    return out


# ---------------- landing page "try it" ----------------

TRY_ITEM = {
    "who": "Victor, a hotel CEO",
    "objection": "We already have a vendor for that, and honestly, you're more expensive.",
    "difficulty": 3,
    "hints": ["acknowledge the vendor without trashing them", "ask what they'd change about the current vendor",
              "tie price to value or cost of the problem", "keep it short"],
    "model_answer": "Makes sense, and I'm not going to bash them. If you could change one thing about how they're "
                    "working for you, what would it be? If we can't beat that, I'm not worth the extra money.",
}


@app.post("/api/try")
def try_one(req: Say, request: Request):
    ratelimit.check("try:" + ratelimit.client_ip(request), 8, 3600, "Nice reps! Make a free account to keep going.")
    text = req.text.strip()[:400]
    if not text:
        raise HTTPException(400, "Say something first.")
    try:
        grade = gauntlet.ai_grade(TRY_ITEM, text) if llm.ai_on() else gauntlet.demo_grade(TRY_ITEM, text)
    except Exception as e:
        log.warning("Try grading failed: %s", e)
        grade = gauntlet.demo_grade(TRY_ITEM, text)
    score = max(0, min(10, engine.to_int(grade.get("score"), 0)))
    return {"score": score, "verdict": grade.get("verdict", ""), "good": grade.get("good", ""),
            "missed": grade.get("missed", ""), "better": grade.get("better") or TRY_ITEM["model_answer"]}


# ---------------- spot the mistake ----------------

@app.post("/api/mistakes")
def start_mistakes(request: Request):
    user = auth.current_user(request)
    run = mistakes.start(user["id"] if user else None)
    return {"run_id": run["id"], "round": mistakes.current(run)}


@app.post("/api/mistakes/{run_id}/ready")
def mistakes_ready(run_id: str, request: Request):
    run = get_run(mistakes.RUNS, run_id, request)
    if run["done"]:
        raise HTTPException(400, "This run is over.")
    return mistakes.ready(run)


def finish_mistakes(run, out):
    # after a call is locked: hand back the next call, or save and summarize the run
    if run["done"]:
        summary = mistakes.summary(run)
        summary["new_best"] = False
        if run["user_id"] and not run["saved"]:
            summary["new_best"] = new_best(run["user_id"], "mistake", run["score"])
            db.save_result(run["user_id"], "mistake", "general", "", "completed", run["score"],
                           round(100 * run["total_found"] / max(1, run["total_mistakes"])),
                           turns=len(run["reviews"]))
            run["saved"] = True
        out["summary"] = summary
    else:
        out["next"] = mistakes.current(run)
    return out


@app.post("/api/mistakes/{run_id}/tap")
def mistakes_tap(run_id: str, req: Pick, request: Request):
    run = get_run(mistakes.RUNS, run_id, request)
    try:
        out = mistakes.tap(run, req.index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return finish_mistakes(run, out) if "review" in out else out


@app.post("/api/mistakes/{run_id}/classify")
def mistakes_classify(run_id: str, req: Classify, request: Request):
    run = get_run(mistakes.RUNS, run_id, request)
    try:
        return mistakes.classify(run, req.index, req.type)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/mistakes/{run_id}/lock")
def mistakes_lock(run_id: str, request: Request):
    run = get_run(mistakes.RUNS, run_id, request)
    if run["done"]:
        raise HTTPException(400, "This run is over.")
    return finish_mistakes(run, mistakes.lock(run))


# ---------------- clutch call ----------------

@app.get("/api/clutch")
def clutch_list():
    return clutch.public_list()


@app.post("/api/clutch/{scenario_id}/start")
def clutch_start(scenario_id: str, request: Request):
    if scenario_id not in clutch.BY_ID:
        raise HTTPException(404, "Unknown call.")
    user = auth.current_user(request)
    run = clutch.start(scenario_id, user["id"] if user else None)
    info = next(x for x in clutch.public_list() if x["id"] == scenario_id)
    return {"run_id": run["id"], "scenario": info, "moment": clutch.current(run)}


@app.post("/api/clutch-runs/{run_id}/ready")
def clutch_ready(run_id: str, request: Request):
    run = get_run(clutch.RUNS, run_id, request)
    if run["done"]:
        raise HTTPException(400, "This call is over.")
    return clutch.ready(run)


@app.post("/api/clutch-runs/{run_id}/pick")
def clutch_pick(run_id: str, req: ClutchPick, request: Request):
    run = get_run(clutch.RUNS, run_id, request)
    try:
        result = clutch.pick(run, req.choice)
    except ValueError as e:
        raise HTTPException(400, str(e))
    out = {"result": result}
    if run["done"]:
        summary = clutch.summary(run)
        summary["new_best"] = False
        if run["user_id"] and not run["saved"]:
            summary["new_best"] = new_best(run["user_id"], "clutch", run["score"])
            s = run["scenario"]
            db.save_result(run["user_id"], "clutch", s["category"], s["id"], clutch.OUTCOME_FOR_DB[run["outcome"]],
                           run["score"], round(100 * run["bests"] / len(s["moments"])),
                           best_combo=run["best_streak"], turns=len(run["picks"]))
            run["saved"] = True
        out["summary"] = summary
    else:
        out["next"] = clutch.current(run)
    return out


# ---------------- leaderboard + profiles ----------------

MODES = ("call", "gauntlet", "daily", "mistake", "clutch")


@app.get("/api/leaderboard")
def leaderboard(request: Request, period: str = "all", category: str = "", mode: str = "call"):
    if period not in ("all", "week") or mode not in MODES:
        raise HTTPException(400, "Bad filter.")
    extra = daily.today() if mode == "daily" else None
    rows = db.leaderboard(period, category or None, mode, extra=extra, verified_only=mailer.enabled())
    me = auth.current_user(request)
    out = []
    for i, r in enumerate(rows):
        out.append({
            "place": i + 1,
            "username": r["username"],
            "display_name": r["display_name"],
            "color": r["color"],
            "score": r["score"],
            "revenue": r["revenue"],
            "plays": r["plays"],
            "wins": r["wins"],
            "rank": profiles.rank_for(db.career_points(r["id"]))["name"],
            "is_me": bool(me and me["id"] == r["id"]),
        })
    return out


@app.get("/api/profile/me")
def my_profile(request: Request):
    user = auth.require_user(request)
    return {"user": auth.public_user(user), "stats": profiles.build_profile(user), "plan": plans.summary(user)}


@app.put("/api/profile")
def update_profile(req: ProfileUpdate, request: Request):
    user = auth.require_user(request)
    name = req.display_name.strip()
    if not 1 <= len(name) <= 30:
        raise HTTPException(400, "Display name has to be 1-30 characters.")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", req.color):
        raise HTTPException(400, "Pick a valid color.")
    db.update_user(user["id"], name, req.color, req.bio.strip()[:160])
    return auth.public_user(db.get_user(user["id"]))


@app.get("/api/users/{username}")
def public_profile(username: str):
    user = db.find_user(username)
    if not user or user["username"].lower() != username.lower():
        raise HTTPException(404, "No player with that username.")
    stats = profiles.build_profile(user)
    stats.pop("weak_spot", None)  # that's private coaching
    return {"user": auth.public_user(user), "stats": stats}


# ---------------- admin ----------------

@app.get("/api/admin/overview")
def admin_overview(request: Request):
    require_admin(request)
    users = [{"id": u["id"], "username": u["username"], "email": u["email"], "plan": u["plan"],
              "verified": bool(u["email_verified"]), "admin": bool(u["is_admin"]), "points": u["points"],
              "plays": u["plays"], "created_at": u["created_at"]} for u in db.all_users()]
    results = [{"id": r["id"], "username": r["username"], "mode": r["mode"], "character_id": r["character_id"],
                "outcome": r["outcome"], "points": r["points"], "created_at": r["created_at"]}
               for r in db.recent_results(50)]
    ai = {"mode": llm.MODE, "models": llm.GROQ_MODELS if llm.MODE == "groq" else [], **llm.STATS,
          "cooling_down": [m for m, t in llm.COOLDOWN.items() if t > time.time()]}
    ai["voice"] = {"provider": voice.PROVIDER, **voice.STATS}
    return {"users": users, "results": results, "ai": ai}


@app.post("/api/admin/users/{user_id}/plan")
def admin_set_plan(user_id: int, req: NewPlan, request: Request):
    require_admin(request)
    if req.plan not in ("free", "pro"):
        raise HTTPException(400, "Plan has to be free or pro.")
    db.set_plan(user_id, req.plan)
    log.info("Admin set user %s to %s", user_id, req.plan)
    return {"ok": True}


@app.delete("/api/admin/results/{result_id}")
def admin_delete_result(result_id: int, request: Request):
    require_admin(request)
    db.delete_result(result_id)
    log.info("Admin deleted result %s", result_id)
    return {"ok": True}


# ---------------- frontend ----------------

@app.middleware("http")
async def always_check_for_new_files(request: Request, call_next):
    # without this, Chrome keeps using old copies of the css/js after an update
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")
