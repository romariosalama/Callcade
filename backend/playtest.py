"""
Playtest the AI buyers without clicking through the website.

Runs a few scripted calls (a good rep and a bad rep) against the real AI and
saves every line, mood change and coaching note to playtest_output.txt.

    cd backend
    python playtest.py
"""

import os
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
os.environ["CALLCADE_DB"] = os.path.join(tempfile.gettempdir(), "callcade_playtest.db")

import db  # noqa: E402
import engine  # noqa: E402
import llm  # noqa: E402

SCRIPTS = [
    ("skeptical-sam", "GOOD rep", [
        "Hi Sam, it's Alex with CloudTrim. I'll be honest, this is a sales call. Can I have 30 seconds to tell you why I called, and you tell me if it's worth more?",
        "We help IT teams find cloud spend nobody's watching. Curious, how is your team keeping an eye on the AWS bill right now?",
        "Makes sense. When something does slip through, like a server nobody turned off, how do you usually find out?",
        "Ouch. Did the CFO say anything when that bill came in?",
        "That's fair, you shouldn't take my word for it. A logistics company about your size cut 22 percent in 60 days, and I can show you exactly how we measured it. What would you need to see to believe a number like that?",
        "Totally fair worry. Nothing gets shut down automatically unless you turn that on. By default it just flags things and your team decides.",
        "And on false positives, that's exactly why it starts in read-only mode. You'd see every flag with the reason and the dollar amount before anyone touches anything. Does that address it?",
        "With the CFO wanting answers by quarter end, what would a good outcome look like for you personally?",
        "Would 20 minutes Thursday at 10 make sense? I'll run it against your actual bill so you're not guessing, and you'll have something concrete for the CFO.",
    ]),
    ("skeptical-sam", "BAD rep", [
        "Hi, how's your day going today?",
        "Awesome! So I'm with CloudTrim, we're a revolutionary AI-powered cloud optimization platform that uses cutting-edge machine learning to cut your AWS costs by 30 percent guaranteed, and we work with hundreds of companies.",
        "Trust me, it works. Can we set up a demo tomorrow?",
        "If you sign up this week I can give you 40 percent off.",
    ]),
    ("payment-only-paula", "GOOD rep (inbound)", [
        "Thanks for calling Coastline Motors, this is Mike! Happy to help with that. So I get you the right number, what monthly payment would feel comfortable?",
        "Got it, four hundred. Can I ask what's got you shopping this week?",
        "Oh no, Saturday's close. How far do you drive for work?",
        "Okay, so reliability really matters. I can get you close to four hundred, and I'd rather show you the total cost honestly than stretch the loan forever. Can you come by at 5 today? I'll have it ready so you're in and out.",
    ]),
    ("burned-brenda", "GOOD rep (door)", [
        "Hi, I'm Chris with SunPeak. I'll be quick, I'm doing energy checks on the street today.",
        "I hear you, and I'm sorry that happened to your neighbor. What happened with him, if you don't mind me asking?",
        "That's awful, and honestly it happens way too much in this industry. If you ever did look at it again, what would need to be different?",
        "That's fair. What's your bill running in the summer?",
        "Four hundred with the AC on all day. No loans, no surprises: could I come back Thursday when your husband's up and show you both the real numbers from your own bill?",
    ]),
]


def run():
    if not llm.ai_on():
        print("AI is off. Set CALLCADE_MODE=groq (or another AI mode) in .env first.")
        sys.exit(1)
    if os.path.exists(os.environ["CALLCADE_DB"]):
        os.remove(os.environ["CALLCADE_DB"])
    db.setup()
    out = []
    for cid, label, lines in SCRIPTS:
        call = engine.start_call(cid)
        c = call.character
        out.append(f"\n===== {c['nickname']} :: {label} :: mode={llm.MODE} =====")
        out.append(f"BUYER: {call.turns[0].text}")
        for line in lines:
            if call.status != "live":
                break
            time.sleep(4)  # a real person takes a few seconds to talk, and it keeps us under Groq's free limit
            before = call.mood
            t0 = time.time()
            try:
                turn = engine.rep_says(call, line)
            except Exception as e:
                out.append(f"REP:   {line}\n  !! ERROR: {e}")
                break
            out.append(f"REP:   {line}")
            out.append(f"BUYER: {turn.text}")
            out.append(f"  mood {before}->{call.mood}  pains={sorted(call.pains_revealed)}  handled={sorted(call.objections_handled)}"
                       f"  status={call.status}  {time.time() - t0:.1f}s  model={llm.STATS.get('last_model', '-')}")
            out.append(f"  why: {turn.note}")
        engine.end_call(call)
        out.append(f"RESULT: {call.status}, final mood {call.mood}")
        print("\n".join(out[-3:]))
        # save after every call, so a crash halfway still leaves something to read
        Path(__file__).parent.joinpath("playtest_output.txt").write_text("\n".join(out))
    print("\nSaved to backend/playtest_output.txt")


if __name__ == "__main__":
    run()
