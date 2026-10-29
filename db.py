"""All database access. Plain functions, no Gradio."""
import json
import os
import secrets
import time
from contextlib import contextmanager
from datetime import date, timedelta

import psycopg2
import psycopg2.extras

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY, name TEXT NOT NULL, level TEXT NOT NULL,
    salt TEXT NOT NULL, hash TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    email TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    expires DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS quizzes (
    code TEXT PRIMARY KEY, creator_email TEXT NOT NULL, title TEXT NOT NULL,
    seconds_per_question INT NOT NULL, max_players INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    quiz_code TEXT NOT NULL REFERENCES quizzes(code) ON DELETE CASCADE,
    position INT NOT NULL, question TEXT NOT NULL,
    options JSONB NOT NULL, answer_index INT NOT NULL
);
CREATE TABLE IF NOT EXISTS players (
    quiz_code TEXT NOT NULL REFERENCES quizzes(code) ON DELETE CASCADE,
    email TEXT NOT NULL, nickname TEXT NOT NULL,
    joined_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (quiz_code, email)
);
CREATE TABLE IF NOT EXISTS attempts (
    id SERIAL PRIMARY KEY, quiz_code TEXT NOT NULL, email TEXT NOT NULL,
    question_id INT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    chosen INT, correct BOOLEAN NOT NULL, seconds REAL NOT NULL, points INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (email, question_id)
);
"""


@contextmanager
def _conn():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Set it to your Neon connection string.")
    con = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with _conn() as con, con.cursor() as cur:
        cur.execute(SCHEMA)


# ---------- accounts and sessions ----------
def get_user(email):
    with _conn() as con, con.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()


def create_user(email, name, level, salt, hash_):
    with _conn() as con, con.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, name, level, salt, hash) VALUES (%s, %s, %s, %s, %s)",
            (email, name, level, salt, hash_),
        )


def create_session(token_hash, email, expires):
    with _conn() as con, con.cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE expires < %s", (time.time(),))
        cur.execute(
            "INSERT INTO sessions (token_hash, email, expires) VALUES (%s, %s, %s)",
            (token_hash, email, expires),
        )


def get_session(token_hash):
    with _conn() as con, con.cursor() as cur:
        cur.execute("SELECT * FROM sessions WHERE token_hash = %s", (token_hash,))
        return cur.fetchone()


def delete_session(token_hash):
    with _conn() as con, con.cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))


# ---------- quizzes ----------
def create_quiz(creator_email, title, seconds_per_question, max_players, questions):
    with _conn() as con, con.cursor() as cur:
        for _ in range(20):
            code = str(secrets.randbelow(900000) + 100000)  # 6 digits
            cur.execute("SELECT 1 FROM quizzes WHERE code = %s", (code,))
            if not cur.fetchone():
                break
        else:
            raise RuntimeError("Could not generate a unique game code.")
        cur.execute(
            "INSERT INTO quizzes (code, creator_email, title, seconds_per_question, max_players) "
            "VALUES (%s, %s, %s, %s, %s)",
            (code, creator_email, title, seconds_per_question, max_players),
        )
        for pos, q in enumerate(questions):
            cur.execute(
                "INSERT INTO questions (quiz_code, position, question, options, answer_index) "
                "VALUES (%s, %s, %s, %s, %s)",
                (code, pos, q["question"], json.dumps(q["options"]), q["answer_index"]),
            )
    return code


def get_quiz(code):
    with _conn() as con, con.cursor() as cur:
        cur.execute("SELECT * FROM quizzes WHERE code = %s", (code,))
        return cur.fetchone()


def question_ids(code):
    with _conn() as con, con.cursor() as cur:
        cur.execute("SELECT id FROM questions WHERE quiz_code = %s ORDER BY position", (code,))
        return [r["id"] for r in cur.fetchall()]


def get_question(question_id):
    with _conn() as con, con.cursor() as cur:
        cur.execute("SELECT * FROM questions WHERE id = %s", (question_id,))
        return cur.fetchone()


def answered_ids(code, email):
    with _conn() as con, con.cursor() as cur:
        cur.execute(
            "SELECT question_id FROM attempts WHERE quiz_code = %s AND email = %s", (code, email)
        )
        return {r["question_id"] for r in cur.fetchall()}


# ---------- playing ----------
def join_quiz(code, email, nickname):
    """Returns (ok, message). Enforces the max-players limit."""
    with _conn() as con, con.cursor() as cur:
        cur.execute("SELECT max_players FROM quizzes WHERE code = %s FOR UPDATE", (code,))
        quiz = cur.fetchone()
        if not quiz:
            return False, "No game found with that code."
        cur.execute("SELECT 1 FROM players WHERE quiz_code = %s AND email = %s", (code, email))
        if cur.fetchone():
            return True, ""
        cur.execute("SELECT COUNT(*) AS n FROM players WHERE quiz_code = %s", (code,))
        if cur.fetchone()["n"] >= quiz["max_players"]:
            return False, "This game is full."
        cur.execute(
            "INSERT INTO players (quiz_code, email, nickname) VALUES (%s, %s, %s)",
            (code, email, nickname),
        )
    return True, ""


def save_attempt(code, email, question_id, chosen, correct, seconds, points):
    with _conn() as con, con.cursor() as cur:
        cur.execute(
            "INSERT INTO attempts (quiz_code, email, question_id, chosen, correct, seconds, points) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (email, question_id) DO NOTHING",
            (code, email, question_id, chosen, correct, seconds, points),
        )


def player_score(code, email):
    """Returns (xp, correct_count, answered_count) for one player in one game."""
    with _conn() as con, con.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(SUM(points), 0) AS xp, "
            "COALESCE(SUM(CASE WHEN correct THEN 1 ELSE 0 END), 0) AS right_count, "
            "COUNT(*) AS answered FROM attempts WHERE quiz_code = %s AND email = %s",
            (code, email),
        )
        r = cur.fetchone()
        return int(r["xp"]), int(r["right_count"]), int(r["answered"])


# ---------- leaderboard and stats ----------
def leaderboard(code=None, limit=20):
    with _conn() as con, con.cursor() as cur:
        if code:
            cur.execute(
                "SELECT p.nickname AS name, COALESCE(SUM(a.points), 0) AS xp "
                "FROM players p LEFT JOIN attempts a "
                "ON a.quiz_code = p.quiz_code AND a.email = p.email "
                "WHERE p.quiz_code = %s GROUP BY p.nickname, p.email "
                "ORDER BY xp DESC, name LIMIT %s",
                (code, limit),
            )
        else:
            cur.execute(
                "SELECT u.name AS name, SUM(a.points) AS xp "
                "FROM attempts a JOIN users u ON u.email = a.email "
                "GROUP BY u.email, u.name ORDER BY xp DESC LIMIT %s",
                (limit,),
            )
        return cur.fetchall()


def user_stats(email):
    with _conn() as con, con.cursor() as cur:
        cur.execute("SELECT COALESCE(SUM(points), 0) AS xp FROM attempts WHERE email = %s", (email,))
        xp = int(cur.fetchone()["xp"])
        cur.execute(
            "SELECT COUNT(DISTINCT quiz_code) AS n FROM attempts WHERE email = %s", (email,)
        )
        played = int(cur.fetchone()["n"])
        cur.execute(
            "SELECT DISTINCT created_at::date AS d FROM attempts WHERE email = %s ORDER BY d DESC",
            (email,),
        )
        days = [r["d"] for r in cur.fetchall()]

    streak = 0
    if days and days[0] >= date.today() - timedelta(days=1):
        expected = days[0]
        for d in days:
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            else:
                break
    return {"xp": xp, "played": played, "streak": streak}