# run with: pytest   (from the project folder)
# these use demo mode and a fake AI, so they need no API keys and don't cost anything

import os
import sys
from pathlib import Path

import pytest

os.environ["CALLCADE_DB"] = str(Path(__file__).parent / "test.db")
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import db  # noqa: E402
import engine  # noqa: E402
import gauntlet  # noqa: E402
import llm  # noqa: E402
import scoring  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    import ratelimit
    ratelimit.reset()
    engine.CALLS.clear()
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    db.setup()
    yield
    os.remove(db.DB_PATH)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import app
    return TestClient(app.app)


def fake_ai(monkeypatch, answers):
    """Make the 'AI' return these answers in order."""
    monkeypatch.setattr(llm, "MODE", "bedrock")
    answers = list(answers)
    monkeypatch.setattr(llm, "ask_for_json", lambda *a, **k: answers.pop(0))


def say(call, *lines):
    for line in lines:
        engine.rep_says(call, line)


# ---------------- data ----------------

def test_all_categories_and_buyers_load():
    assert list(engine.CATEGORIES) == ["tech", "real-estate", "life-insurance", "car-sales", "solar"]
    assert len(engine.CHARACTERS) == 40
    needed = ["nickname", "stars", "bio", "buyer", "rules", "voice", "hidden_pains", "objections", "close_condition",
              "upsell", "deal_value", "objections_to_win", "meeting_threshold", "demo_lines"]
    for c in engine.CHARACTERS.values():
        for key in needed:
            assert key in c, (c["id"], key)
        assert len(c["hidden_pains"]) == 3 and len(c["objections"]) >= 3
    for cat in engine.CATEGORIES.values():
        assert sum(1 for c in cat["characters"] if c.get("boss")) == 1
        assert [c["level"] for c in cat["characters"]] == list(range(1, 9))  # 8 levels everywhere
        assert cat["characters"][-1].get("boss")


def test_objection_bank():
    cats = {o["category"] for o in gauntlet.OBJECTIONS}
    assert cats == {"general", "tech", "real-estate", "life-insurance", "car-sales", "solar"}
    assert len({o["id"] for o in gauntlet.OBJECTIONS}) == len(gauntlet.OBJECTIONS)


# ---------------- harder rules ----------------

def test_ai_cant_book_meeting_before_objections_are_handled(monkeypatch):
    fake_ai(monkeypatch, [{"reply": "Sure, let's meet!", "mood_change": 10, "pains_revealed": [0], "outcome": "meeting_booked"}])
    call = engine.start_call("easy-eddie")
    call.mood = 90
    say(call, "Can we meet Tuesday?")
    assert call.status == "live"
    assert call.turns[-1].text == call.character["objections"][0]  # pushed back instead
    assert call.pending_objection == 0


def test_handling_objection_then_booking(monkeypatch):
    fake_ai(monkeypatch, [
        {"reply": "What about card fees?", "mood_change": 3, "pains_revealed": [0], "objection_raised": 2, "outcome": "continue"},
        {"reply": "Oh, okay, that's not bad.", "mood_change": 6, "outcome": "continue"},
        {"reply": "Alright, Tuesday works.", "mood_change": 4, "outcome": "meeting_booked"},
    ])
    call = engine.start_call("easy-eddie")
    say(call, "How are lunch rushes going?", "Totally fair. What are you paying in fees now?", "Can we do a demo Tuesday?")
    assert call.objections_handled == {2}
    assert call.status == "meeting_booked"


def test_ai_cant_close_a_cold_buyer(monkeypatch):
    fake_ai(monkeypatch, [{"reply": "Sure!", "mood_change": 0, "outcome": "closed"}])
    call = engine.start_call("cold-claire")
    say(call, "Want to buy?")
    assert call.status == "live"


def test_mood_gain_is_capped_by_difficulty(monkeypatch):
    fake_ai(monkeypatch, [{"reply": "Wow!", "mood_change": 999, "outcome": "continue"}])
    call = engine.start_call("victor")
    say(call, "Hi")
    assert call.mood == call.character["starting_mood"] + 5  # boss cap


def test_pushy_pitch_gets_door_closed():
    call = engine.start_call("no-soliciting-nancy")
    say(call, "Hi! Our revolutionary, game-changing solar leverages synergy. Sign today, limited time offer!")
    assert call.status == "hung_up"


def test_demo_eddie_takes_real_work():
    call = engine.start_call("easy-eddie")
    say(call, "Hi Eddie, can we set up a demo tomorrow?")
    assert call.status == "live"  # nobody just says yes


def test_warm_lead():
    call = engine.start_call("easy-eddie")
    call.mood = 70
    call.turns += [engine.Turn("rep", "hi", 70)] * 3
    engine.end_call(call)
    assert call.status == "follow_up"


# ---------------- scoring ----------------

def test_discount_detection():
    assert scoring.discount_offered("I can do 20% off if you sign today") == 20
    assert scoring.discount_offered("We help 30 percent of teams") == 0
    assert scoring.discount_offered("I'll cut my commission from 2.5% to 2%") == 2


def test_close_with_upsell_scores_revenue(monkeypatch):
    call = engine.start_call("easy-eddie")
    call.status = "closed"
    call.upsold = True
    call.turns.append(engine.Turn("rep", "Want to get started on all three trucks today?", 90))
    card = scoring.scorecard(call)
    c = call.character
    assert card["points"]["revenue"] == c["deal_value"]["close"] + c["deal_value"]["upsell"]
    assert card["category"] == "tech"


def test_multipliers():
    for cid, mult in [("easy-eddie", 1.0), ("technical-theo", 2.0), ("victor", 3.0), ("investor-ivan", 3.0)]:
        call = engine.start_call(cid)
        assert scoring.scorecard(call)["points"]["multiplier"] == mult


def test_filler_words():
    call = engine.start_call("chatty-charlie")
    say(call, "Um, so, uh, basically I wanted to check in, you know?")
    assert scoring.metrics(call)["filler_count"] == 4


def test_parse_json_with_code_fence():
    assert llm.parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}


# ---------------- gauntlet ----------------

def test_gauntlet_run():
    run = gauntlet.start("real-estate")
    assert len(run["items"]) == 10
    for _ in range(10):
        gauntlet.answer(run, "That's fair, I hear you. What would make it worth it for you, so you net more money?")
    s = gauntlet.summary(run)
    assert run["done"] and len(s["answers"]) == 10 and s["total"] > 0


def test_gauntlet_grades_bad_answers_low():
    item = gauntlet.OBJECTIONS[0]
    assert gauntlet.demo_grade(item, "ok")["score"] <= 3
    good = gauntlet.demo_grade(item, "Totally fair. So I send the right information, what would you want it to answer? It usually saves time.")
    assert good["score"] >= 7


def test_gauntlet_three_strikes_and_youre_out():
    run = gauntlet.start("mixed")
    for _ in range(3):
        r = gauntlet.answer(run, "ok")
        assert r["lost_life"]
    assert run["done"] and run["knocked_out"] and len(run["answers"]) == 3
    s = gauntlet.summary(run)
    assert s["knocked_out"] and s["rounds_played"] == 3 and s["avg_score"] <= 1


def test_gauntlet_clock_shrinks_and_last_round_is_boss():
    run = gauntlet.start("mixed")
    first = gauntlet.current_round(run)
    assert first["time_limit"] == 30 and not first["boss"] and first["lives"] == 3
    run["answers"] = [{}] * 9  # pretend we got to the end
    last = gauntlet.current_round(run)
    assert last["time_limit"] == 15 and last["boss"]


def test_gauntlet_generic_answers_cant_score_high():
    item = next(o for o in gauntlet.OBJECTIONS if o["difficulty"] == 3)
    generic = gauntlet.demo_grade(item, "Totally fair, I hear you. What would make it worth it for you?")
    assert generic["score"] <= 5


def test_gauntlet_timeout(monkeypatch):
    run = gauntlet.start("mixed")
    run["round_started"] -= 60
    r = gauntlet.answer(run, "Great question, what do you mean?")
    assert r["score"] == 0


# ---------------- accounts + API ----------------

def test_signup_login_logout(client):
    r = client.post("/api/auth/signup", json={"username": "romario", "email": "r@test.com", "password": "password123"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "romario"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json() is None
    assert client.post("/api/auth/login", json={"login": "r@test.com", "password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"login": "ROMARIO", "password": "password123"}).status_code == 200


def test_signup_validation(client):
    bad = [
        {"username": "a", "email": "r@test.com", "password": "password123"},
        {"username": "romario", "email": "nope", "password": "password123"},
        {"username": "romario", "email": "r@test.com", "password": "short"},
    ]
    for form in bad:
        assert client.post("/api/auth/signup", json=form).status_code == 400
    client.post("/api/auth/signup", json={"username": "romario", "email": "r@test.com", "password": "password123"})
    client.post("/api/auth/logout")
    r = client.post("/api/auth/signup", json={"username": "Romario", "email": "x@test.com", "password": "password123"})
    assert r.status_code == 400


def test_password_is_hashed(client):
    client.post("/api/auth/signup", json={"username": "romario", "email": "r@test.com", "password": "password123"})
    row = db.find_user("romario")
    assert "password123" not in row["password_hash"]


def test_locked_levels_and_saving(client):
    client.post("/api/auth/signup", json={"username": "romario", "email": "r@test.com", "password": "password123"})
    assert client.post("/api/calls", json={"character_id": "chatty-charlie"}).status_code == 403

    call_id = client.post("/api/calls", json={"character_id": "easy-eddie"}).json()["call_id"]
    engine.CALLS[call_id].status = "meeting_booked"  # pretend they won
    card = client.post(f"/api/calls/{call_id}/end").json()
    assert card["progress"]["unlocked"][0]["id"] == "chatty-charlie"
    assert client.post("/api/calls", json={"character_id": "chatty-charlie"}).status_code == 200

    board = client.get("/api/leaderboard").json()
    assert board[0]["username"] == "romario" and board[0]["is_me"]
    profile = client.get("/api/profile/me").json()
    assert profile["stats"]["calls"] == 1 and profile["stats"]["wins"] == 1


def test_guests_can_play_but_dont_save(client):
    call_id = client.post("/api/calls", json={"character_id": "first-time-fiona"}).json()["call_id"]
    card = client.post(f"/api/calls/{call_id}/end").json()
    assert card["progress"] is None
    assert client.get("/api/leaderboard").json() == []


def test_cant_touch_someone_elses_call(client):
    client.post("/api/auth/signup", json={"username": "romario", "email": "r@test.com", "password": "password123"})
    call_id = client.post("/api/calls", json={"character_id": "easy-eddie"}).json()["call_id"]
    client.post("/api/auth/logout")
    assert client.post(f"/api/calls/{call_id}/say", json={"text": "hi"}).status_code == 403


def test_profile_update_and_public_profile(client):
    client.post("/api/auth/signup", json={"username": "romario", "email": "r@test.com", "password": "password123"})
    r = client.put("/api/profile", json={"display_name": "Romario G", "color": "#ff0000", "bio": "closer"})
    assert r.json()["display_name"] == "Romario G"
    assert client.put("/api/profile", json={"display_name": "x", "color": "red"}).status_code == 400
    assert client.get("/api/users/romario").json()["user"]["bio"] == "closer"
    assert client.get("/api/users/r@test.com").status_code == 404  # no looking people up by email


def test_hidden_info_never_sent_to_browser(client):
    text = client.get("/api/categories").text
    for c in engine.CHARACTERS.values():
        assert c["hidden_pains"][0] not in text
        assert c["rules"] not in text


def test_voice_falls_back_without_polly(client):
    r = client.post("/api/voice", json={"character_id": "easy-eddie", "text": "hello"})
    assert r.status_code == 204


def test_gauntlet_api_saves_best(client):
    client.post("/api/auth/signup", json={"username": "romario", "email": "r@test.com", "password": "password123"})
    run = client.post("/api/gauntlet", json={"category": "solar"}).json()
    for _ in range(10):
        r = client.post(f"/api/gauntlet/{run['run_id']}/answer", json={"text": "Totally fair. What's your bill running now, so we can see the savings?"}).json()
    assert r["summary"]["new_best"] is True
    assert client.get("/api/leaderboard?mode=gauntlet").json()[0]["score"] == r["summary"]["total"]


def test_claude_api_mode(monkeypatch):
    # fake Anthropic client so we can check the call without a real API key
    class Msg:
        content = [type("T", (), {"text": '{"reply": "Who is this?", "mood_change": -2, "outcome": "continue"}'})()]

    class FakeClient:
        class messages:
            @staticmethod
            def create(**kwargs):
                assert kwargs["messages"][0]["role"] == "user"
                return Msg()

    monkeypatch.setattr(llm, "MODE", "claude")
    monkeypatch.setattr(llm, "_client", FakeClient())
    call = engine.start_call("easy-eddie")
    say(call, "hey")
    assert call.turns[-1].text == "Who is this?"
    assert call.mood == call.character["starting_mood"] - 2


def test_practice_bot_handles_nonsense():
    call = engine.start_call("easy-eddie")
    say(call, "Sunderland")
    assert call.turns[-1].text in ["Sorry, what?", "...What do you mean?", "I'm sorry, who is this?", "Uh, okay?"]
    assert call.mood < call.character["starting_mood"]


# ---------------- plans ----------------

def signup(client, name="romario", industry="tech"):
    r = client.post("/api/auth/signup", json={"username": name, "email": name + "@test.com",
                                              "password": "password123", "free_category": industry})
    assert r.status_code == 200
    return db.find_user(name)


def win(client, character_id):
    call_id = client.post("/api/calls", json={"character_id": character_id}).json()["call_id"]
    engine.CALLS[call_id].status = "meeting_booked"
    client.post(f"/api/calls/{call_id}/end")


def test_guests_only_get_level_1(client):
    assert client.post("/api/calls", json={"character_id": "easy-eddie"}).status_code == 200
    assert client.post("/api/calls", json={"character_id": "fsbo-frank"}).status_code == 403
    assert client.post("/api/calls", json={"character_id": "victor"}).status_code == 403
    assert client.post("/api/gauntlet", json={"category": "mixed"}).status_code == 401
    locks = {c["id"]: c["lock"] for cat in client.get("/api/categories").json() for c in cat["characters"]}
    assert locks["easy-eddie"] == "" and locks["chatty-charlie"] == "signup"


def test_free_plan_limits(client):
    signup(client, industry="real-estate")
    assert client.post("/api/calls", json={"character_id": "easy-eddie"}).status_code == 403  # other industry
    assert client.post("/api/calls", json={"character_id": "zillow-zack"}).status_code == 403  # not unlocked yet
    win(client, "first-time-fiona")
    win(client, "zillow-zack")
    win(client, "downsizing-dolores")
    r = client.post("/api/calls", json={"character_id": "fsbo-frank"})  # level 4 is pro
    assert r.status_code == 403 and "Pro" in r.json()["detail"]
    locks = {c["id"]: c["lock"] for cat in client.get("/api/categories").json() for c in cat["characters"]}
    assert locks["fsbo-frank"] == "pro" and locks["victor"] == "pro"


def test_free_daily_call_limit(client):
    signup(client)
    for _ in range(10):
        assert client.post("/api/calls", json={"character_id": "easy-eddie"}).status_code == 200
    assert client.post("/api/calls", json={"character_id": "easy-eddie"}).status_code == 429
    assert client.get("/api/plan").json()["calls_left"] == 0


def test_free_gauntlet_limit(client):
    signup(client)
    for _ in range(3):
        assert client.post("/api/gauntlet", json={"category": "mixed"}).status_code == 200
    assert client.post("/api/gauntlet", json={"category": "mixed"}).status_code == 429


def test_pro_gets_everything_but_still_unlocks_in_order(client):
    user = signup(client)
    db.set_plan(user["id"], "pro")
    assert client.post("/api/calls", json={"character_id": "curious-carl"}).status_code == 200
    assert client.post("/api/calls", json={"character_id": "no-soliciting-nancy"}).status_code == 403
    win(client, "curious-carl")
    assert client.post("/api/calls", json={"character_id": "no-soliciting-nancy"}).status_code == 200
    for _ in range(15):
        assert client.post("/api/calls", json={"character_id": "curious-carl"}).status_code == 200  # no daily cap


def test_switch_free_industry_once_a_month(client):
    signup(client)
    assert client.post("/api/plan/industry", json={"category": "solar"}).json()["free_category"] == "solar"
    assert client.post("/api/plan/industry", json={"category": "tech"}).status_code == 400


def test_old_database_gets_new_columns():
    import sqlite3
    os.remove(db.DB_PATH)
    conn = sqlite3.connect(db.DB_PATH)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT, password_hash TEXT, "
                 "display_name TEXT, color TEXT, bio TEXT, created_at TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'old', 'o@test.com', 'x$y', 'Old', '#fff', '', '2026-01-01')")
    conn.commit()
    conn.close()
    db.setup()
    user = db.get_user(1)
    assert user["plan"] == "free" and user["free_category"] == "tech"


def test_ollama_mode(monkeypatch):
    class Res:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"message": {"content": '{"reply": "Uh, who is this?", "mood_change": "-3", "pains_revealed": ["0"], "outcome": "continue"}'}}

    monkeypatch.setattr(llm, "MODE", "ollama")
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: Res())
    call = engine.start_call("easy-eddie")
    say(call, "Sunderland")
    assert call.turns[-1].text == "Uh, who is this?"
    assert call.mood == call.character["starting_mood"] - 3
    assert call.pains_revealed == {0}


# ---------------- saved calls, daily, challenges, game modes, accounts ----------------

import mailer  # noqa: E402


def last_link(kind):
    body = mailer.outbox[-1]["body"]
    return body.split(f"#/{kind}?token=")[1].split()[0]


def test_calls_survive_a_restart(client):
    call_id = client.post("/api/calls", json={"character_id": "easy-eddie"}).json()["call_id"]
    client.post(f"/api/calls/{call_id}/say", json={"text": "Hi Eddie, this is Sam. How's the lunch rush going?"})
    engine.CALLS.clear()  # pretend the server restarted
    r = client.post(f"/api/calls/{call_id}/say", json={"text": "That makes sense. What's the hardest part?"})
    assert r.status_code == 200
    assert len(engine.get(call_id).turns) == 5


def test_one_open_call_at_a_time(client):
    signup(client)
    first = client.post("/api/calls", json={"character_id": "easy-eddie"}).json()["call_id"]
    client.post("/api/calls", json={"character_id": "easy-eddie"})
    engine.CALLS.clear()
    assert client.post(f"/api/calls/{first}/say", json={"text": "hello there"}).status_code == 404


def test_daily_challenge_one_scored_try(client):
    signup(client)
    info = client.get("/api/daily").json()
    assert info["played"] is None and info["character"]["level"] >= 2  # works even though it's locked for them
    call_id = client.post("/api/daily/start").json()["call_id"]
    card = client.post(f"/api/calls/{call_id}/end").json()
    assert card["kind"] == "daily" and card["result_id"]
    assert client.get("/api/daily").json()["played"] is not None
    assert client.post("/api/daily/start").status_code == 400


def test_challenge_a_friend(client):
    signup(client, "romario")
    call_id = client.post("/api/calls", json={"character_id": "easy-eddie"}).json()["call_id"]
    engine.CALLS[call_id].status = "meeting_booked"
    card = client.post(f"/api/calls/{call_id}/end").json()
    code = client.post("/api/challenges", json={"result_id": card["result_id"]}).json()["code"]
    client.post("/api/auth/logout")

    info = client.get(f"/api/challenges/{code}").json()
    assert info["from"]["username"] == "romario" and info["character"]["id"] == "easy-eddie"
    call_id = client.post(f"/api/challenges/{code}/start").json()["call_id"]
    card = client.post(f"/api/calls/{call_id}/end").json()
    assert card["challenge"]["their_points"] == info["points"]
    assert card["challenge"]["won"] is False


def test_cant_challenge_with_someone_elses_result(client):
    signup(client, "romario")
    call_id = client.post("/api/calls", json={"character_id": "easy-eddie"}).json()["call_id"]
    result_id = client.post(f"/api/calls/{call_id}/end").json()["result_id"]
    client.post("/api/auth/logout")
    signup(client, "other")
    assert client.post("/api/challenges", json={"result_id": result_id}).status_code == 400


def test_mistake_data_is_solid():
    import mistakes
    assert len(mistakes.CALLS) >= 8
    for c in mistakes.CALLS:
        assert len(c["lines"]) >= 18, c["id"]
        m = mistakes.mistakes_in(c)
        assert 3 <= len(m) <= 4, c["id"]
        reps = [i for i, (who, _) in enumerate(c["lines"]) if who == "rep"]
        assert all(i in reps for i in m), c["id"]      # mistakes are always rep lines
        assert len(reps) - len(m) >= 5, c["id"]        # plenty of good rep lines as decoys
        assert all(v["type"] in mistakes.TYPES for v in m.values())


def test_spot_the_mistake_full_run(client):
    signup(client)
    run = client.post("/api/mistakes").json()
    assert not {"mistakes", "why", "fix", "type"} & set(run["round"])  # answers stay on the server
    import mistakes
    r = mistakes.RUNS[run["run_id"]]
    # call 1: find everything and name it right = perfect
    m = mistakes.mistakes_in(r["calls"][0])
    for i, v in m.items():
        hit = client.post(f"/api/mistakes/{run['run_id']}/tap", json={"index": i}).json()
        assert hit["hit"] and len(hit["options"]) == 4 and v["type"] in [o["id"] for o in hit["options"]]
        named = client.post(f"/api/mistakes/{run['run_id']}/classify", json={"index": i, "type": v["type"]}).json()
        assert named["right"]
    out = client.post(f"/api/mistakes/{run['run_id']}/lock").json()
    assert out["review"]["perfect"] and out["review"]["bonus"] >= mistakes.PERFECT and "next" in out
    # call 2: tap three good lines and you're out of lives
    good = [i for i, (who, _) in enumerate(r["calls"][1]["lines"]) if who == "rep" and i not in mistakes.mistakes_in(r["calls"][1])]
    for i in good[:3]:
        out = client.post(f"/api/mistakes/{run['run_id']}/tap", json={"index": i}).json()
    assert out["done"] and out["summary"]["lives"] == 0
    assert out["review"]["missed"] == len(mistakes.mistakes_in(r["calls"][1]))
    assert client.get("/api/leaderboard?mode=mistake").json()[0]["score"] == out["summary"]["score"]


def test_mistake_rules(client):
    run = client.post("/api/mistakes").json()
    rid = run["run_id"]
    assert client.post(f"/api/mistakes/{rid}/tap", json={"index": 0 if run["round"]["lines"][0][0] == "buyer" else 2}).status_code in (400, 200)
    buyer_line = next(i for i, (who, _) in enumerate(run["round"]["lines"]) if who == "buyer")
    assert client.post(f"/api/mistakes/{rid}/tap", json={"index": buyer_line}).status_code == 400
    assert client.post(f"/api/mistakes/{rid}/classify", json={"index": 1, "type": "discount"}).status_code == 400


def test_clutch_call(client):
    import clutch
    assert len(clutch.SCENARIOS) == 5
    for s in clutch.SCENARIOS:
        for m in s["moments"]:
            assert sorted(o["grade"] for o in m["options"]) == ["bad", "best", "good", "worst"]
    signup(client)
    start = client.post("/api/clutch/cfo/start").json()
    assert "grade" not in str(start["moment"]) and len(start["moment"]["options"]) == 4
    run = clutch.RUNS[start["run_id"]]
    # always pick the best line
    for i in range(6):
        m = run["scenario"]["moments"][run["i"]]
        order = run["order"][run["i"]]
        k = next(k for k, j in enumerate(order) if m["options"][j]["grade"] == "best")
        out = client.post(f"/api/clutch-runs/{start['run_id']}/pick", json={"choice": k}).json()
        assert out["result"]["grade"] == "best"
    s = out["summary"]
    assert s["outcome"] == "win" and s["bests"] == 6 and s["score"] > 1600
    assert client.get("/api/leaderboard?mode=clutch").json()[0]["score"] == s["score"]


def test_clutch_bad_picks_get_you_hung_up(client):
    import clutch
    start = client.post("/api/clutch/brenda/start").json()
    run = clutch.RUNS[start["run_id"]]
    for _ in range(3):
        if run["done"]:
            break
        m = run["scenario"]["moments"][run["i"]]
        order = run["order"][run["i"]]
        k = next(k for k, j in enumerate(order) if m["options"][j]["grade"] == "worst")
        out = client.post(f"/api/clutch-runs/{start['run_id']}/pick", json={"choice": k}).json()
    assert run["done"] and out["summary"]["outcome"] == "lose" and "hung up" in out["summary"]["ending"]
    # timing out counts as freezing
    start = client.post("/api/clutch/tina/start").json()
    out = client.post(f"/api/clutch-runs/{start['run_id']}/pick", json={"choice": None}).json()
    assert out["result"]["grade"] == "froze"


def test_try_it_on_the_landing_page(client):
    r = client.post("/api/try", json={"text": "Makes sense. If you could change one thing about your vendor, what would it be?"}).json()
    assert 0 <= r["score"] <= 10 and r["better"]
    for _ in range(8):
        client.post("/api/try", json={"text": "ok"})
    assert client.post("/api/try", json={"text": "ok"}).status_code == 429


def test_forgot_and_reset_password(client):
    signup(client)
    client.post("/api/auth/logout")
    assert client.post("/api/account/forgot", json={"email": "nobody@test.com"}).json()["ok"]  # same answer
    client.post("/api/account/forgot", json={"email": "romario@test.com"})
    token = last_link("reset")
    assert client.post("/api/account/reset", json={"token": token, "password": "newpass123"}).status_code == 200
    assert client.post("/api/account/reset", json={"token": token, "password": "again1234"}).status_code == 400  # one use
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"login": "romario", "password": "newpass123"}).status_code == 200


def test_verify_email(client):
    signup(client)
    token = last_link("verify")
    assert client.get("/api/auth/me").json()["email_verified"] is False
    assert client.post("/api/account/verify", json={"token": token}).status_code == 200
    assert client.get("/api/auth/me").json()["email_verified"] is True


def test_change_password_and_logout_everywhere(client):
    signup(client)
    assert client.post("/api/account/password", json={"current": "wrong", "new": "whatever123"}).status_code == 400
    assert client.post("/api/account/password", json={"current": "password123", "new": "brandnew123"}).status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "romario"  # still logged in here
    client.post("/api/account/logout-everywhere")
    assert client.get("/api/auth/me").json() is None


def test_delete_account(client):
    signup(client)
    client.post("/api/calls", json={"character_id": "easy-eddie"})
    assert client.post("/api/account/delete", json={"password": "nope"}).status_code == 400
    assert client.post("/api/account/delete", json={"password": "password123"}).status_code == 200
    assert db.find_user("romario") is None


def test_login_rate_limit(client):
    signup(client)
    client.post("/api/auth/logout")
    codes = [client.post("/api/auth/login", json={"login": "romario", "password": "bad"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[-1] == 429


def test_admin_only(client):
    user = signup(client)
    assert client.get("/api/admin/overview").status_code == 403
    db.set_admin(user["id"], True)
    data = client.get("/api/admin/overview").json()
    assert data["users"][0]["username"] == "romario"
    assert client.post(f"/api/admin/users/{user['id']}/plan", json={"plan": "pro"}).json()["ok"]
    assert db.get_user(user["id"])["plan"] == "pro"


def test_admin_can_play_everything(client):
    user = signup(client)
    boss = next(c for c in engine.CHARACTERS.values() if c["category"] == "solar" and c.get("boss"))
    assert client.post("/api/calls", json={"character_id": boss["id"]}).status_code == 403
    db.set_admin(user["id"], True)
    assert client.post("/api/calls", json={"character_id": boss["id"]}).status_code == 200
    assert client.get("/api/plan").json()["calls_left"] is None


def test_timezone_setting(client):
    signup(client)
    assert client.post("/api/account/timezone", json={"timezone": "Mars/Base"}).status_code == 400
    assert client.post("/api/account/timezone", json={"timezone": "America/New_York"}).status_code == 200
    assert db.find_user("romario")["timezone"] == "America/New_York"


def test_streaks():
    import profiles
    from datetime import datetime, timedelta, timezone
    tz = timezone.utc
    today = datetime.now(tz)
    rows = [{"created_at": (today - timedelta(days=d)).isoformat()} for d in (0, 1, 2, 5, 6)]
    assert profiles.streaks(rows, tz) == (3, 3)
    rows = [{"created_at": (today - timedelta(days=d)).isoformat()} for d in (3, 4)]
    assert profiles.streaks(rows, tz) == (0, 2)


def test_weak_spot_and_progress(client):
    signup(client)
    for _ in range(3):
        call_id = client.post("/api/calls", json={"character_id": "easy-eddie"}).json()["call_id"]
        client.post(f"/api/calls/{call_id}/say", json={"text": "Our revolutionary synergy platform is the best in the world and you need it"})
        client.post(f"/api/calls/{call_id}/end")
    stats = client.get("/api/profile/me").json()["stats"]
    assert len(stats["progress"]) == 3
    assert stats["weak_spot"] is not None
    assert stats["streak"] == 1


# ---------------- real phone calls + build your own buyer ----------------

def test_calls_start_with_just_hello():
    call = engine.start_call("easy-eddie")
    assert call.turns[0].text == "Hello?"
    for c in engine.CHARACTERS.values():
        if not c.get("inbound"):
            assert len(engine.pickup_line(c).split()) <= 7, c["id"]  # a short hello, not a speech
    # once you say who you are, they react
    engine.rep_says(call, "Hi Eddie, this is Sam with TapTab. Got a quick second?")
    assert call.turns[-1].text == engine.CHARACTERS["easy-eddie"]["opening_line"]


def test_buyer_asks_who_this_is_if_you_dont_introduce_yourself():
    call = engine.start_call("easy-eddie")
    engine.rep_says(call, "Hey, do you have a quick second to talk about payments?")
    assert call.turns[-1].text == "Sorry, who is this?"


BUILD = {"sell": "Payroll software for restaurants, about $6 per employee a month",
         "customer": "A restaurant owner who hates software, does payroll on paper, and thinks every rep is lying",
         "difficulty": 4}


def test_build_a_buyer_without_ai(client):
    signup(client)
    b = client.post("/api/custom-buyers", json=BUILD).json()
    assert b["custom"] and b["id"].startswith("custom-") and b["stars"] == 4
    assert "hidden_pains" not in b and "objections" not in b  # still secret
    assert client.get("/api/custom-buyers").json()[0]["id"] == b["id"]
    start = client.post("/api/calls", json={"character_id": b["id"]}).json()
    assert start["buyer_says"] == "Hello?" and start["kind"] == "custom"
    client.post(f"/api/calls/{start['call_id']}/say", json={"text": "Hi, this is Sam from PayPlate. How do you run payroll today?"})
    card = client.post(f"/api/calls/{start['call_id']}/end").json()
    assert card["result_id"]
    r = db.get_result(card["result_id"])
    assert r["mode"] == "custom" and r["points"] == 0  # can't farm points with an easy buyer
    assert client.get("/api/leaderboard?mode=call").json() == []


def test_build_a_buyer_with_ai(client, monkeypatch):
    fake_ai(monkeypatch, [{"nickname": "Paper-Payroll Pete", "gender": "male", "traits": "Stubborn, old school",
                           "bio": "Pete has done payroll by hand for 20 years.", "buyer": {"name": "Pete Rossi"},
                           "hidden_pains": ["I spend every Sunday on payroll."], "objections": ["I don't trust computers."]}])
    signup(client)
    b = client.post("/api/custom-buyers", json=BUILD).json()
    assert b["nickname"] == "Paper-Payroll Pete" and b["buyer"]["name"] == "Pete Rossi"
    c = db.get_custom_buyer(b["id"])
    assert len(c["hidden_pains"]) == 3 and len(c["objections"]) == 3  # filled in the rest
    assert c["objections"][0] == "I don't trust computers."


def test_build_limits(client):
    assert client.post("/api/custom-buyers", json={**BUILD, "sell": "hi"}).status_code == 400
    signup(client)
    for _ in range(3):
        assert client.post("/api/custom-buyers", json=BUILD).status_code == 200
    assert client.post("/api/custom-buyers", json=BUILD).status_code == 429


# ---------------- realism ----------------

def test_every_buyer_has_realism_and_a_full_prompt():
    for c in engine.CHARACTERS.values():
        for key in ("context", "real_talk", "wins", "turn_offs"):
            assert c.get(key), (c["id"], key)
        call = engine.start_call(c["id"])
        p = engine.buyer_prompt(call)
        assert "HOW REAL BUYERS ACT" in p and "Wins you over" in p and "EXAMPLE of a real call" in p, c["id"]
        assert c["real_talk"][0] in p
        assert len(p.split()) < 1400, (c["id"], len(p.split()))  # keep it small enough for Groq's free plan
        assert 4 <= engine.strong_line_value(c) <= engine.max_gain(c)


def test_inbound_calls_start_with_the_customer_talking():
    call = engine.start_call("payment-only-paula")
    assert call.turns[0].text == engine.CHARACTERS["payment-only-paula"]["opening_line"]
    assert "YOU made to the dealership" in engine.buyer_prompt(call)
    engine.rep_says(call, "Thanks for calling! Happy to help. What payment are you hoping to stay under?")
    assert call.turns[-1].text != "Sorry, who is this?"


def test_custom_buyers_still_get_the_general_realism(client):
    signup(client)
    b = client.post("/api/custom-buyers", json=BUILD).json()
    call = engine.start_call(b["id"])
    p = engine.buyer_prompt(call)
    assert "HOW REAL BUYERS ACT" in p and "EXAMPLE of a real call" not in p


def test_groq_falls_back_to_the_next_model_when_one_is_maxed_out(monkeypatch):
    import httpx

    class Res:
        def __init__(self, code, text="", headers=None):
            self.status_code, self.text, self.headers = code, text, headers or {}

        def json(self):
            return {"choices": [{"message": {"content": '{"reply": "Yeah?"}'}}]}

        def raise_for_status(self):
            pass

    tried = []

    def fake_post(url, json, headers, timeout):
        tried.append(json["model"])
        return Res(429, headers={"retry-after": "30"}) if json["model"] == llm.GROQ_MODELS[0] else Res(200)

    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(httpx, "post", fake_post)
    llm.COOLDOWN.clear()
    assert llm.ask_groq("system", [{"role": "user", "content": "hi"}], 100) == '{"reply": "Yeah?"}'
    assert tried[:2] == llm.GROQ_MODELS[:2]
    # the maxed-out model is skipped next time instead of wasting a request
    tried.clear()
    llm.ask_groq("system", [{"role": "user", "content": "hi"}], 100)
    assert tried == [llm.GROQ_MODELS[1]]
    llm.COOLDOWN.clear()


def test_ai_grades_turn_into_fair_points(monkeypatch):
    fake_ai(monkeypatch, [{"rating": "good", "reply": f"Hm. Go on, part {i}."} for i in range(4)] +
            [{"rating": "great", "reply": "Okay, fine.", "objection_handled": True}])
    call = engine.start_call("skeptical-sam")
    say(call, "line one", "line two", "line three", "line four")
    strong = engine.strong_line_value(call.character)
    assert call.mood == 30 + 4 * strong  # 'good' is worth a strong line for this buyer
    say(call, "line five")
    assert len(call.objections_handled) == 1  # counted even though the AI didn't name the objection


def test_no_hang_up_on_a_normal_opener(monkeypatch):
    fake_ai(monkeypatch, [{"rating": "weak", "reply": "Not interested.", "outcome": "hung_up"}])
    call = engine.start_call("burned-brenda")
    say(call, "Hi, I'm Chris with SunPeak. I'll be quick, I'm doing energy checks on the street today.")
    assert call.status == "live"


def test_ai_echo_gets_retried(monkeypatch):
    fake_ai(monkeypatch, [{"rating": "good", "reply": "Got it, four hundred."}, {"rating": "good", "reply": "My car failed smog."}])
    call = engine.start_call("payment-only-paula")
    say(call, "Got it, four hundred.")
    assert call.turns[-1].text == "My car failed smog."


def test_saying_yes_counts_when_the_rep_did_the_work(monkeypatch):
    fake_ai(monkeypatch, [{"rating": "good", "reply": "Thursday at 10 works.", "outcome": "meeting_booked"}])
    call = engine.start_call("skeptical-sam")
    c = call.character
    call.mood = c["meeting_threshold"] - 10
    call.objections_raised |= {0, 1}
    call.objections_handled |= {0, 1}
    call.pains_revealed.add(0)
    say(call, "Would 20 minutes Thursday at 10 make sense?")
    assert call.status == "meeting_booked"


# ---------------- voices ----------------

def _wav(n):
    import io
    import wave
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x00" * n)
    return b.getvalue()


def test_orpheus_voice_setup_for_every_buyer():
    import voice
    for c in engine.CHARACTERS.values():
        name, style = voice.orpheus_voice(c["voice"])
        assert name in voice.ORPHEUS_VOICES[c["voice"]["gender"]], c["id"]
        assert style.startswith("["), c["id"]
    long = "This is a sentence. " * 30
    assert all(len(p) <= 180 for p in voice.chunks(long))
    assert voice.clean("*sighs* [annoyed] Fine. What?") == "Fine. What?"
    assert voice.mood_style("[friendly]", 10) == "[irritated]" and voice.mood_style("[friendly]", 80) == "[warm]"


def test_groq_voice_splits_long_lines_and_joins_audio(monkeypatch):
    import httpx
    import voice

    sent = []

    class Res:
        status_code = 200
        content = _wav(100)
        text = ""

    def fake_post(url, timeout, headers, json):
        sent.append(json)
        return Res()

    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(httpx, "post", fake_post)
    audio, mime = voice.groq_speak("Short one. " + "A much longer sentence that goes on. " * 8, engine.CHARACTERS["cold-claire"]["voice"], 50)
    assert mime == "audio/wav" and len(sent) >= 2
    assert all(s["voice"] == "diana" and s["input"].startswith("[deadpan]") for s in sent)
    import io
    import wave
    with wave.open(io.BytesIO(audio)) as w:
        assert w.getnframes() == 100 * len(sent)


def test_voice_failure_falls_back_to_the_browser(monkeypatch):
    import voice
    monkeypatch.setattr(voice, "ENABLED", True)
    monkeypatch.setattr(voice, "PROVIDER", "groq")
    monkeypatch.setattr(voice, "groq_speak", lambda *a: (_ for _ in ()).throw(RuntimeError("Groq voice 429")))
    assert voice.speak("Hello there.", engine.CHARACTERS["easy-eddie"]["voice"], 50) is None
    assert voice.STATS["failed"] >= 1


def test_joining_streamed_wavs_with_unknown_length():
    import voice
    real = _wav(50)
    streamed = real[:4] + (0xFFFFFFFF).to_bytes(4, "little") + real[8:40] + (0xFFFFFFFF).to_bytes(4, "little") + real[44:]
    joined = voice.join_wavs([streamed, streamed])
    import io
    import wave
    with wave.open(io.BytesIO(joined)) as w:
        assert w.getnframes() == 100
