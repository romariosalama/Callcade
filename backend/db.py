"""
Database stuff. Using SQLite because it's built into Python and is just one
file (callcade.db). When I deploy this I can swap it for a hosted database.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = os.getenv("CALLCADE_DB", str(Path(__file__).parent / "callcade.db"))


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets me do row["username"]
    return conn


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# small helpers so every function doesn't have to open and close the connection itself
def execute(sql, params=()):
    conn = connect()
    cur = conn.execute(sql, params)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def fetch_one(sql, params=()):
    conn = connect()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def fetch_all(sql, params=()):
    conn = connect()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def add_column(conn, table, column, definition):
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def setup():
    conn = connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#ff6b35',
            bio TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mode TEXT NOT NULL,             -- call, gauntlet, daily, challenge, mistake, clutch, custom
            category TEXT NOT NULL,
            character_id TEXT,
            outcome TEXT NOT NULL,
            points INTEGER NOT NULL,
            skill INTEGER NOT NULL,
            revenue INTEGER NOT NULL DEFAULT 0,
            best_combo INTEGER NOT NULL DEFAULT 0,
            badges TEXT NOT NULL DEFAULT '[]',
            turns INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,             -- 'call', 'gauntlet' or 'build'
            created_at TEXT NOT NULL
        );

        -- one-time links for resetting a password or verifying an email
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,             -- 'reset' or 'verify'
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );

        -- calls that are still going, so a server restart doesn't lose them
        CREATE TABLE IF NOT EXISTS active_calls (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS challenges (
            code TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            result_id INTEGER NOT NULL,
            character_id TEXT NOT NULL,
            points INTEGER NOT NULL,
            outcome TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS custom_buyers (
            id TEXT PRIMARY KEY,
            user_id INTEGER,                -- null for guests
            data TEXT NOT NULL,             -- the whole buyer, same shape as the ones in data/
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_results_user ON results(user_id);
        CREATE INDEX IF NOT EXISTS idx_results_created ON results(created_at);
        CREATE INDEX IF NOT EXISTS idx_usage_user ON usage(user_id, kind, created_at);
    """)

    # older databases need the newer columns added
    add_column(conn, "users", "plan", "TEXT NOT NULL DEFAULT 'free'")
    add_column(conn, "users", "free_category", "TEXT")
    add_column(conn, "users", "free_category_set_at", "TEXT")
    add_column(conn, "users", "timezone", "TEXT NOT NULL DEFAULT 'America/Los_Angeles'")
    add_column(conn, "users", "email_verified", "INTEGER NOT NULL DEFAULT 0")
    add_column(conn, "users", "is_admin", "INTEGER NOT NULL DEFAULT 0")
    add_column(conn, "results", "extra", "TEXT NOT NULL DEFAULT ''")      # e.g. the date of a daily challenge
    add_column(conn, "results", "details", "TEXT NOT NULL DEFAULT '{}'")  # skill breakdown, for weak spots
    conn.execute("UPDATE users SET free_category = 'tech' WHERE free_category IS NULL")

    # calls nobody touched in a day are abandoned
    day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM active_calls WHERE updated_at < ?", (day_ago,))
    conn.commit()
    conn.close()


# ---------------- users ----------------

def create_user(username, email, password_hash, display_name, color, free_category="tech", tz="America/Los_Angeles"):
    return execute(
        """INSERT INTO users (username, email, password_hash, display_name, color, free_category, timezone, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (username, email, password_hash, display_name, color, free_category, tz, now()),
    )


def find_user(username_or_email):
    return fetch_one("SELECT * FROM users WHERE lower(username) = lower(?) OR lower(email) = lower(?)",
                     (username_or_email, username_or_email))


def get_user(user_id):
    return fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


def update_user(user_id, display_name, color, bio):
    execute("UPDATE users SET display_name = ?, color = ?, bio = ? WHERE id = ?", (display_name, color, bio, user_id))


def set_password(user_id, password_hash):
    execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def set_timezone(user_id, tz):
    execute("UPDATE users SET timezone = ? WHERE id = ?", (tz, user_id))


def set_verified(user_id):
    execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))


def set_admin(user_id, is_admin):
    execute("UPDATE users SET is_admin = ? WHERE id = ?", (1 if is_admin else 0, user_id))


def all_users():
    return fetch_all("""
        SELECT users.*, COALESCE(SUM(results.points), 0) AS points, COUNT(results.id) AS plays
        FROM users LEFT JOIN results ON results.user_id = users.id
        GROUP BY users.id ORDER BY users.id DESC
    """)


def delete_user(user_id):
    conn = connect()
    for table in ("sessions", "results", "usage", "tokens", "active_calls", "challenges", "custom_buyers"):
        conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


# ---------------- sessions ----------------

def create_session(token, user_id):
    execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, user_id, now()))


def session_user(token):
    if not token:
        return None
    return fetch_one("SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = ?",
                     (token,))


def delete_session(token):
    execute("DELETE FROM sessions WHERE token = ?", (token,))


def delete_all_sessions(user_id):
    execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


# ---------------- reset / verify tokens ----------------

def create_token(token, user_id, kind, hours):
    expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")
    execute("INSERT INTO tokens (token, user_id, kind, expires_at) VALUES (?, ?, ?, ?)", (token, user_id, kind, expires))


def use_token(token, kind):
    # the user id if the token is real, unused and not expired. marks it used
    row = fetch_one("SELECT * FROM tokens WHERE token = ? AND kind = ? AND used = 0", (token, kind))
    if not row or row["expires_at"] < now():
        return None
    execute("UPDATE tokens SET used = 1 WHERE token = ?", (token,))
    return row["user_id"]


# ---------------- results ----------------

def save_result(user_id, mode, category, character_id, outcome, points, skill, revenue=0,
                best_combo=0, badges=None, turns=0, extra="", details=None):
    return execute(
        """INSERT INTO results (user_id, mode, category, character_id, outcome, points, skill, revenue,
                                best_combo, badges, turns, extra, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, mode, category, character_id or "", outcome, points, skill, revenue,
         best_combo, json.dumps(badges or []), turns, extra, json.dumps(details or {}), now()),
    )


def get_result(result_id):
    return fetch_one("SELECT * FROM results WHERE id = ?", (result_id,))


def delete_result(result_id):
    execute("DELETE FROM results WHERE id = ?", (result_id,))


def user_results(user_id, limit=None):
    sql = "SELECT * FROM results WHERE user_id = ? ORDER BY created_at DESC, id DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return fetch_all(sql, (user_id,))


def recent_results(limit=100):
    return fetch_all("""SELECT results.*, users.username FROM results JOIN users ON users.id = results.user_id
                        ORDER BY results.id DESC LIMIT ?""", (limit,))


# modes where your best single run counts, instead of adding everything up
BEST_RUN_MODES = ("gauntlet", "mistake", "clutch", "daily")


def leaderboard(period="all", category=None, mode="call", limit=50, extra=None, verified_only=False):
    where = ["results.mode = ?"]
    params = [mode]
    if category:
        where.append("results.category = ?")
        params.append(category)
    if extra:
        where.append("results.extra = ?")
        params.append(extra)
    if period == "week":
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
        where.append("results.created_at >= ?")
        params.append(week_ago)
    if verified_only:
        where.append("users.email_verified = 1")

    score = "MAX(results.points)" if mode in BEST_RUN_MODES else "SUM(results.points)"
    sql = f"""
        SELECT users.id, users.username, users.display_name, users.color,
               {score} AS score,
               SUM(results.revenue) AS revenue,
               COUNT(*) AS plays,
               SUM(CASE WHEN results.outcome IN ('closed', 'meeting_booked') THEN 1 ELSE 0 END) AS wins
        FROM results JOIN users ON users.id = results.user_id
        WHERE {' AND '.join(where)}
        GROUP BY users.id
        ORDER BY score DESC, revenue DESC
        LIMIT ?
    """
    params.append(limit)
    return fetch_all(sql, params)


def career_points(user_id):
    # custom buyers don't count, otherwise you could build an easy one and farm points
    return fetch_one("SELECT COALESCE(SUM(points), 0) AS pts FROM results WHERE user_id = ? AND mode != 'custom'",
                     (user_id,))["pts"]


# ---------------- plans + usage ----------------

def set_plan(user_id, plan):
    execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))


def set_free_category(user_id, category):
    execute("UPDATE users SET free_category = ?, free_category_set_at = ? WHERE id = ?", (category, now(), user_id))


def add_usage(user_id, kind):
    execute("INSERT INTO usage (user_id, kind, created_at) VALUES (?, ?, ?)", (user_id, kind, now()))


def count_usage(user_id, kind, since):
    return fetch_one("SELECT COUNT(*) AS n FROM usage WHERE user_id = ? AND kind = ? AND created_at >= ?",
                     (user_id, kind, since))["n"]


# ---------------- active calls ----------------

def save_active_call(call_id, user_id, data):
    execute("INSERT OR REPLACE INTO active_calls (id, user_id, data, updated_at) VALUES (?, ?, ?, ?)",
            (call_id, user_id, json.dumps(data), now()))


def load_active_call(call_id):
    row = fetch_one("SELECT * FROM active_calls WHERE id = ?", (call_id,))
    return json.loads(row["data"]) if row else None


def delete_active_call(call_id):
    execute("DELETE FROM active_calls WHERE id = ?", (call_id,))


def delete_user_active_calls(user_id):
    rows = fetch_all("SELECT id FROM active_calls WHERE user_id = ?", (user_id,))
    execute("DELETE FROM active_calls WHERE user_id = ?", (user_id,))
    return [r["id"] for r in rows]


# ---------------- challenges ----------------

def create_challenge(code, user_id, result_id, character_id, points, outcome):
    execute("""INSERT INTO challenges (code, user_id, result_id, character_id, points, outcome, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""", (code, user_id, result_id, character_id, points, outcome, now()))


def get_challenge(code):
    return fetch_one("""SELECT challenges.*, users.username, users.display_name, users.color FROM challenges
                        JOIN users ON users.id = challenges.user_id WHERE code = ?""", (code,))


def challenge_for_result(result_id):
    return fetch_one("SELECT * FROM challenges WHERE result_id = ?", (result_id,))


# ---------------- custom buyers ----------------

def save_custom_buyer(buyer_id, user_id, data):
    execute("INSERT OR REPLACE INTO custom_buyers (id, user_id, data, created_at) VALUES (?, ?, ?, ?)",
            (buyer_id, user_id, json.dumps(data), now()))


def get_custom_buyer(buyer_id):
    row = fetch_one("SELECT * FROM custom_buyers WHERE id = ?", (buyer_id,))
    if not row:
        return None
    data = json.loads(row["data"])
    data["owner_id"] = row["user_id"]
    return data


def user_custom_buyers(user_id, limit=12):
    rows = fetch_all("SELECT data FROM custom_buyers WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
    return [json.loads(r["data"]) for r in rows]


def delete_custom_buyer(buyer_id, user_id):
    execute("DELETE FROM custom_buyers WHERE id = ? AND user_id = ?", (buyer_id, user_id))
