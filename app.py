import base64
import hashlib
import hmac
import inspect
import math
import os
import re
import secrets
import time
from pathlib import Path

import gradio as gr

import db
import scoring
from model.generate_mcq import generate_from_text, generate_mcqs

# ---------------------------------------------------------
# Files: logo at DataBot/assets/knowva-logo.png
# Accounts, login sessions, quizzes and scores live in the
# Postgres database set by the DATABASE_URL environment variable.
# ---------------------------------------------------------
BASE_DIR = Path(__file__).parent
LOGO_PATH = BASE_DIR / "assets" / "knowva-logo.png"

SESSION_DAYS = 30  # how long you stay logged in (change this number if you like)


def logo_as_text(path):
    """Turn the logo file into text so it can be placed directly in the page."""
    if not path.exists():
        print(f"Logo not found at: {path}")
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{data}"


LOGO_DATA = logo_as_text(LOGO_PATH)

# Create the database tables if they don't exist yet.
# This stops with a clear error if DATABASE_URL is not set.
db.init_db()


# ---------------------------------------------------------
# Accounts (stored in the database)
# ---------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password, salt=None):
    """Scramble the password so it is never stored as plain text."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 200_000
    ).hex()
    return salt, digest


# ---------------------------------------------------------
# "Stay logged in" sessions
# The browser keeps a secret code. We only save a scrambled
# copy of it here, so the file alone can't be used to log in.
# ---------------------------------------------------------
def _token_key(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(email):
    token = secrets.token_urlsafe(32)
    db.create_session(_token_key(token), email, time.time() + SESSION_DAYS * 86400)
    return token


def user_from_token(token):
    if not token:
        return None
    session = db.get_session(_token_key(token))
    if not session or session["expires"] < time.time():
        return None
    record = db.get_user(session["email"])
    if not record:
        return None
    return {"name": record["name"], "email": record["email"], "level": record["level"]}


def end_session(token):
    if token:
        db.delete_session(_token_key(token))


# ---------------------------------------------------------
# Styling
# Lavender #F3EFFF | Deep lavender #E3D9FF | Deep purple #301065
# Royal purple #6C3BFF | Light purple #BBA4FF | Yellow #FFD76A
# ---------------------------------------------------------
css = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap');

/* ---- Lock colours so text is always readable ---- */
:root, .dark, .gradio-container {
    --body-text-color: #22212A;
    --body-text-color-subdued: #4D4660;
    --block-background-fill: transparent;
    --block-border-width: 0px;
    --background-fill-primary: transparent;
    --background-fill-secondary: transparent;
    --border-color-primary: transparent;
    --link-text-color: #6C3BFF;
    --slider-color: #6C3BFF;
    color-scheme: light;
}

.gradio-container {
    background-color: #F3EFFF !important;
    background-image:
        linear-gradient(rgba(48, 16, 101, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(48, 16, 101, 0.05) 1px, transparent 1px) !important;
    background-size: 34px 34px !important;
    font-family: 'IBM Plex Sans', 'Segoe UI', sans-serif !important;
}
footer { display: none !important; }

.gradio-container .block {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* ---- Everything sits in the middle ---- */
#shell {
    width: 100%;
    max-width: 1100px;
    margin: 0 auto !important;
    padding: 20px 24px 50px;
}

/* ---- Text styles ---- */
.title h1, .title h2, .title h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    color: #301065 !important;
    letter-spacing: -1px;
}
.centered, .centered * { text-align: center !important; }
.subtle p { color: #4D4660 !important; font-size: 16px; line-height: 1.7; }
.eyebrow {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    letter-spacing: 2px;
    font-weight: 700;
    color: #6C3BFF !important;
}
.view { margin-top: 36px; }

/* ---- Login / sign-up card ---- */
#auth-card {
    width: 100%;
    max-width: 470px;
    margin: 40px auto 0 !important;
    background: #E3D9FF !important;
    border: 1px solid #CDBDFF !important;
    border-radius: 24px !important;
    padding: 32px !important;
    box-shadow: 0 22px 60px rgba(48, 16, 101, 0.16);
}
button[role="tab"] {
    background: transparent !important;
    color: #4D4660 !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
}
button[role="tab"].selected, button[role="tab"][aria-selected="true"] {
    color: #6C3BFF !important;
    border-bottom: 2px solid #6C3BFF !important;
}

/* ---- Inputs ---- */
.gradio-container input, .gradio-container textarea, .gradio-container select {
    background: #F3EFFF !important;
    color: #22212A !important;
    border: 1px solid #BBA4FF !important;
    border-radius: 10px !important;
}
.gradio-container input::placeholder,
.gradio-container textarea::placeholder {
    color: #6B6280 !important;
    opacity: 1;
}
.gradio-container label span, .gradio-container .block-title, .gradio-container [data-testid="block-info"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    color: #301065 !important;
}

/* ---- Top bar and the floating navigation pill ---- */
#topbar { align-items: center; }
#pill-col { align-items: center; }
.nav-pill {
    background: #301065;
    border-radius: 999px;
    padding: 8px 12px !important;
    gap: 6px !important;
    flex-wrap: nowrap !important;
    width: fit-content !important;
    margin: 0 auto;
    box-shadow: 0 14px 40px rgba(48, 16, 101, 0.3);
}
.nav-pill > * {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 100px !important;
}
.nav-pill button {
    background: transparent !important;
    color: #E9E0FF !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 999px !important;
    min-width: 100px !important;
    white-space: nowrap !important;
    padding: 12px 18px !important;
    font-size: 13px !important;
    letter-spacing: 0.3px;
}
.nav-pill button:hover { background: rgba(255, 255, 255, 0.1) !important; }
.nav-pill button.primary {
    background: #FFD76A !important;
    color: #301065 !important;
}
#logout-btn {
    background: transparent !important;
    color: #301065 !important;
    border: 1px solid #BBA4FF !important;
    padding: 10px 18px !important;
}
@media (max-width: 760px) {
    .nav-pill { overflow-x: auto; max-width: 100%; }
}

/* ---- Cards ---- */
.gradio-container div.card {
    background: #E3D9FF !important;
    border: 1px solid #CDBDFF !important;
    border-radius: 16px !important;
    padding: 24px !important;
    transition: transform 0.2s;
}
.gradio-container div.card:hover { transform: translateY(-4px); }
.card h1, .card h2, .card h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    color: #301065 !important;
    margin: 6px 0 !important;
}
.card p { color: #3B3350 !important; line-height: 1.7; }
.stat h1 { font-size: 40px !important; }

/* ---- Dark challenge card ---- */
.gradio-container div.quiz-card {
    background: #301065 !important;
    border-radius: 22px !important;
    padding: 28px !important;
    box-shadow: 0 22px 60px rgba(48, 16, 101, 0.28);
}
.quiz-card *, .banner * { color: #FFFFFF !important; }
.quiz-card .eyebrow { color: #BBA4FF !important; }
.quiz-card h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 21px !important;
    line-height: 1.4;
}
.quiz-card label {
    background: rgba(255, 255, 255, 0.08) !important;
    border: 1px solid rgba(187, 164, 255, 0.4) !important;
    border-radius: 10px !important;
}
.quiz-card strong { color: #FFD76A !important; }

/* ---- Leaderboard table ---- */
.board table { width: 100%; border-collapse: collapse; }
.board th, .board td {
    padding: 12px 10px;
    text-align: left;
    border-bottom: 1px solid #CDBDFF;
    color: #301065 !important;
}
.board th {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    letter-spacing: 1px;
}

/* ---- Buttons ---- */
#create-btn, #login-btn, #signup-btn, #generate-btn, #join-game-btn {
    background: #6C3BFF !important;
    color: white !important;
    border: none !important;
}
#check-btn { background: #FFD76A !important; color: #301065 !important; border: none !important; }
button {
    font-family: 'JetBrains Mono', monospace !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    padding: 14px 22px !important;
}

.footer-note p {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: #4D4660 !important;
    margin-top: 50px !important;
}

/* ---- Option buttons (Secondary school / Undergraduate) ---- */
#auth-card .wrap, .card .wrap {
    display: flex !important;
    flex-wrap: wrap;
    gap: 10px !important;
    background: transparent !important;
}
#auth-card .wrap label, .card .wrap label {
    background: #F3EFFF !important;
    border: 1px solid #BBA4FF !important;
    border-radius: 10px !important;
    padding: 10px 18px !important;
    cursor: pointer;
}
#auth-card .wrap label span, .card .wrap label span {
    color: #301065 !important;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 14px;
}
#auth-card .wrap label.selected, .card .wrap label.selected {
    background: #6C3BFF !important;
    border-color: #6C3BFF !important;
}
#auth-card .wrap label.selected span, .card .wrap label.selected span {
    color: #FFFFFF !important;
}
#auth-card input[type="radio"], .card input[type="radio"] {
    accent-color: #FFD76A;
}

/* ---- Create page: readable colours (normal weight) ---- */
.card button.center {
    background: #F3EFFF !important;
    border: 2px dashed #6C3BFF !important;
    border-radius: 14px !important;
    min-height: 200px;
}
.card .wrap { color: #301065 !important; }
.card .wrap .or { color: #6C3BFF !important; }
.card [data-testid="block-label"] {
    background: #6C3BFF !important;
    color: #FFFFFF !important;
}
.gradio-container input[type="range"] { accent-color: #6C3BFF !important; }
.card input[type="number"] {
    background: #F3EFFF !important;
    border: 1px solid #BBA4FF !important;
    color: #301065 !important;
}
.card .head { background: transparent !important; border: none !important; }

/* ---- Hide Gradio's loading timer ---- */
.meta-text, .meta-text-center, .progress-text { display: none !important; }
"""

# ---------------------------------------------------------
# Pages and navigation
# ---------------------------------------------------------
VIEWS = ["home", "explore", "create", "join", "board"]


def go(view):
    """Show one page, hide the others, and highlight its button in the pill."""
    shown = [gr.update(visible=(v == view)) for v in VIEWS]
    buttons = [gr.update(variant="primary" if v == view else "secondary") for v in VIEWS]
    return shown + buttons


def make_nav(view):
    def _go():
        return go(view)
    return _go


# ---------------------------------------------------------
# Login / sign up actions
# ---------------------------------------------------------
def greeting_text(user):
    first = user["name"].split()[0]
    return (
        f'<span class="eyebrow">// WELCOME BACK · {user["level"].upper()}</span>\n'
        f"## Hello, {first}.\n"
        "Ready to learn something today?"
    )


def _success(user):
    token = create_session(user["email"])
    return (
        [user, "", gr.update(visible=False), gr.update(visible=True), greeting_text(user)]
        + go("home")
        + ["", "", ""]  # clear the password boxes
        + [token]       # saved in the browser so you stay logged in
    )


def _fail(message):
    return (
        [gr.skip(), f"⚠️ {message}", gr.update(), gr.update(), gr.update()]
        + [gr.update()] * (len(VIEWS) * 2 + 3)
        + [gr.skip()]
    )


def log_in(email, password):
    email = (email or "").strip().lower()
    record = db.get_user(email)
    if not record:
        return _fail("Wrong email or password.")
    _, digest = hash_password(password or "", record["salt"])
    if not hmac.compare_digest(digest, record["hash"]):
        return _fail("Wrong email or password.")
    return _success({"name": record["name"], "email": email, "level": record["level"]})


def sign_up(name, email, level, password, confirm):
    name = (name or "").strip()
    email = (email or "").strip().lower()
    if not name or not email or not password:
        return _fail("Please fill in every field.")
    if not EMAIL_RE.match(email):
        return _fail("That email address doesn't look right.")
    if len(password) < 8:
        return _fail("Your password needs at least 8 characters.")
    if password != confirm:
        return _fail("The two passwords don't match.")
    if db.get_user(email):
        return _fail("An account with this email already exists. Try logging in.")
    salt, digest = hash_password(password)
    db.create_user(email, name, level, salt, digest)
    return _success({"name": name, "email": email, "level": level})


def restore_session(token):
    """Runs every time the page opens: log back in if the browser has a valid code."""
    user = user_from_token(token)
    if not user:
        return (
            [None, gr.update(visible=False), gr.update(visible=True),
             gr.update(visible=False), gr.update()]
            + [gr.update()] * (len(VIEWS) * 2)
        )
    return (
        [user, gr.update(visible=False), gr.update(visible=False),
         gr.update(visible=True), greeting_text(user)]
        + go("home")
    )


def log_out(token):
    end_session(token)
    return None, "", gr.update(visible=True), gr.update(visible=False), None


# ---------------------------------------------------------
# Creating a quiz
# ---------------------------------------------------------
def generate_quiz(user, file, notes, count, seconds, max_players):
    if not user:
        return "Please log in first."
    notes = (notes or "").strip()
    if file is None and not notes:
        return "Upload a PDF or TXT file, or paste your notes first."
    try:
        if file is not None:
            path = file if isinstance(file, str) else file.name
            questions = generate_mcqs(path, int(count))
            title = Path(path).stem[:60]
        else:
            questions = generate_from_text(notes, int(count))
            title = notes[:40]
    except ValueError as e:
        return f"⚠️ {e}"
    if not questions:
        return "⚠️ Couldn't make questions from this text. Try longer or clearer notes."
    code = db.create_quiz(user["email"], title, int(seconds), int(max_players), questions)
    return (
        f"✓ Quiz ready with {len(questions)} questions.\n\n"
        f"## Game code: {code}\n"
        f"Share this code. Up to {int(max_players)} players can join."
    )


# ---------------------------------------------------------
# Playing a game
# join_game and submit_answer return values for these outputs, in this order:
# play_state, join_msg, join_form, play_col, play_q, play_choice,
# play_clock, play_msg, play_timer
# ---------------------------------------------------------
def _play_fail(message):
    return [gr.skip(), f"⚠️ {message}"] + [gr.skip()] * 7


def _question_view(ps):
    q = db.get_question(ps["ids"][ps["i"]])
    ps["started"] = time.time()
    choices = [f"{'ABCD'[n]}. {o}" for n, o in enumerate(q["options"])]
    head = f'<span class="eyebrow">QUESTION {ps["i"] + 1} OF {len(ps["ids"])}</span>'
    return (
        f"{head}\n### {q['question']}",
        gr.update(choices=choices, value=None),
        f"⏱ {ps['limit']}s",
    )


def join_game(user, code, nickname):
    if not user:
        return _play_fail("Please log in first.")
    code = (code or "").strip()
    nickname = (nickname or "").strip().replace("|", "/")[:30]
    if not code or not nickname:
        return _play_fail("Enter a game code and a nickname.")
    ok, msg = db.join_quiz(code, user["email"], nickname)
    if not ok:
        return _play_fail(msg)
    done = db.answered_ids(code, user["email"])
    ids = [i for i in db.question_ids(code) if i not in done]
    if not ids:
        return _play_fail("You have already finished this game. Check the Ranks page.")
    quiz = db.get_quiz(code)
    ps = {
        "code": code, "email": user["email"], "ids": ids, "i": 0,
        "limit": quiz["seconds_per_question"], "started": 0,
    }
    q_md, choice, clock = _question_view(ps)
    return [
        ps, "", gr.update(visible=False), gr.update(visible=True),
        q_md, choice, clock, "", gr.Timer(active=True),
    ]


def submit_answer(user, ps, choice):
    if not user or not ps or ps.get("email") != user["email"]:
        return _play_fail("Join a game first.")
    q_id = ps["ids"][ps["i"]]
    q = db.get_question(q_id)
    used = time.time() - ps["started"]
    if not choice and used <= ps["limit"]:
        return [gr.skip()] * 7 + ["Pick an answer first."] + [gr.skip()]

    chosen = "ABCD".index(choice[0]) if choice else None
    correct = chosen == q["answer_index"]
    points = scoring.points_for(correct, used, ps["limit"])
    db.save_attempt(ps["code"], user["email"], q_id, chosen, correct, used, points)

    right = f"{'ABCD'[q['answer_index']]}. {q['options'][q['answer_index']]}"
    if correct and points:
        feedback = f"✓ Correct! **+{points} XP**"
    elif correct:
        feedback = "✓ Correct, but too late for points."
    else:
        feedback = f"✗ Not quite. The answer was **{right}**."

    ps["i"] += 1
    if ps["i"] >= len(ps["ids"]):
        xp, right_count, answered = db.player_score(ps["code"], user["email"])
        final = (
            f"{feedback}\n\n🏁 Finished! You scored **{xp} XP** "
            f"({right_count} of {answered} correct). Check the Ranks page."
        )
        return [
            None, final, gr.update(visible=True), gr.update(visible=False),
            "", gr.update(choices=[], value=None), "", "", gr.Timer(active=False),
        ]
    q_md, choice_update, clock = _question_view(ps)
    return [ps, "", gr.skip(), gr.skip(), q_md, choice_update, clock, feedback, gr.skip()]


def tick(ps):
    """Countdown display only. The real time check happens in submit_answer."""
    if not ps:
        return gr.skip()
    left = ps["limit"] - (time.time() - ps["started"])
    if left > 0:
        return f"⏱ {math.ceil(left)}s"
    return "⏰ Time's up. Submit to move on (0 points)."


# ---------------------------------------------------------
# Leaderboard and Home stats
# ---------------------------------------------------------
def render_board(code):
    rows = db.leaderboard((code or "").strip() or None)
    header = "| RANK | PLAYER | XP |\n|---|---|---|\n"
    if not rows:
        return header + "| - | No scores yet | - |"
    return header + "\n".join(
        f"| {i} | {str(r['name']).replace('|', '/')} | {int(r['xp'] or 0):,} |"
        for i, r in enumerate(rows, 1)
    )


def refresh_stats(user):
    if not user:
        return gr.skip(), gr.skip(), gr.skip()
    s = db.user_stats(user["email"])
    return (
        f'<span class="eyebrow">TOTAL XP</span>\n# {s["xp"]:,}',
        f'<span class="eyebrow">QUIZZES PLAYED</span>\n# {s["played"]}',
        f'<span class="eyebrow">DAY STREAK</span>\n# {s["streak"]}',
    )


def timer_for(view):
    """The Ranks page refreshes itself every few seconds, only while it is open."""
    def _t():
        return gr.Timer(active=(view == "board"))
    return _t


# ---------------------------------------------------------
# Settings that depend on your Gradio version
# ---------------------------------------------------------
blocks_options = {"title": "Knowva | Learn Smarter. Play to Know More."}
launch_options = {
    "server_name": "0.0.0.0",
    "server_port": int(os.environ.get("PORT", 7860)),
    "share": os.environ.get("RENDER") is None,  # public link only on your laptop
}
if "css" in inspect.signature(gr.Blocks.launch).parameters:
    launch_options["css"] = css
else:
    blocks_options["css"] = css


# ---------------------------------------------------------
# The app
# ---------------------------------------------------------
with gr.Blocks(**blocks_options) as demo:

    user_state = gr.State(None)
    play_state = gr.State(None)  # the game the player is in right now (kept on the server)

    # Timers have no visible part. They sit here so they keep working on every page.
    play_timer = gr.Timer(1, active=False)   # question countdown
    board_timer = gr.Timer(5, active=False)  # refreshes the Ranks page

    # Lives in the browser, so it survives refreshes and closing the tab.
    # The storage_key and secret are fixed so it still works after you restart the app.
    session_token = gr.BrowserState(
        None,
        storage_key="knowva_session",
        secret=os.environ.get("KNOWVA_SECRET", "knowva-local-secret"),
    )

    with gr.Column(elem_id="shell"):

        # Shown for a moment while the app checks if you are already logged in
        loading_view = gr.Markdown(
            '<span class="eyebrow">LOADING...</span>',
            visible=True,
            elem_classes=["centered", "view"],
        )

        # =====================================================
        # PAGE 1: LOGIN / SIGN UP
        # =====================================================
        with gr.Column(visible=False, elem_id="auth-card") as auth_view:
            gr.HTML(
                f'<div style="text-align:center;">'
                f'<img src="{LOGO_DATA}" alt="Knowva logo" '
                f'style="height:110px; width:auto; object-fit:contain;"></div>'
            )
            gr.Markdown(
                "## Welcome to Knowva\nLearn smarter. Play to know more.",
                elem_classes=["title", "centered"],
            )

            with gr.Tabs():
                with gr.Tab("Log in"):
                    login_email = gr.Textbox(label="Email", placeholder="you@example.com")
                    login_pw = gr.Textbox(label="Password", type="password")
                    login_btn = gr.Button("Log in  →", elem_id="login-btn")

                with gr.Tab("Sign up"):
                    su_name = gr.Textbox(label="Full name")
                    su_email = gr.Textbox(label="Email", placeholder="you@example.com")
                    su_level = gr.Radio(
                        ["Secondary school", "Undergraduate"],
                        value="Secondary school",
                        label="I am a",
                    )
                    su_pw = gr.Textbox(label="Password (8+ characters)", type="password")
                    su_confirm = gr.Textbox(label="Confirm password", type="password")
                    signup_btn = gr.Button("Create account  →", elem_id="signup-btn")

            auth_msg = gr.Markdown("", elem_classes="centered")

        # =====================================================
        # PAGE 2: THE APP (hidden until you log in)
        # =====================================================
        with gr.Column(visible=False) as app_view:

            # ----- Top bar: logo | navigation pill | log out -----
            with gr.Row(elem_id="topbar"):
                with gr.Column(scale=1, min_width=130):
                    gr.HTML(
                        f'<img src="{LOGO_DATA}" alt="Knowva logo" '
                        f'style="height:72px; width:auto; object-fit:contain;">'
                    )
                with gr.Column(scale=4, min_width=300, elem_id="pill-col"):
                    with gr.Row(elem_classes="nav-pill"):
                        nav_home = gr.Button("⌂  Home", variant="primary", scale=0, min_width=0)
                        nav_explore = gr.Button("◎  Explore", variant="secondary", scale=0, min_width=0)
                        nav_create = gr.Button("✦  Create", variant="secondary", scale=0, min_width=0)
                        nav_join = gr.Button("↗  Join", variant="secondary", scale=0, min_width=0)
                        nav_board = gr.Button("★  Ranks", variant="secondary", scale=0, min_width=0)
                with gr.Column(scale=1, min_width=130):
                    logout_btn = gr.Button("Log out", elem_id="logout-btn", size="sm")

            nav_buttons = [nav_home, nav_explore, nav_create, nav_join, nav_board]

            # ----- HOME -----
            with gr.Column(visible=True, elem_classes="view") as view_home:
                greeting = gr.Markdown("", elem_classes=["title", "centered"])

                with gr.Row():
                    with gr.Column(elem_classes=["card", "stat", "centered"], min_width=200):
                        xp_md = gr.Markdown('<span class="eyebrow">TOTAL XP</span>\n# 0')
                    with gr.Column(elem_classes=["card", "stat", "centered"], min_width=200):
                        played_md = gr.Markdown('<span class="eyebrow">QUIZZES PLAYED</span>\n# 0')
                    with gr.Column(elem_classes=["card", "stat", "centered"], min_width=200):
                        streak_md = gr.Markdown('<span class="eyebrow">DAY STREAK</span>\n# 0')

                with gr.Row(equal_height=False):
                    with gr.Column(elem_classes="card", min_width=300):
                        gr.Markdown(
                            "### ✦ Create a Quiz\n"
                            "Turn your notes or a PDF into practice questions."
                        )
                        home_create = gr.Button("Create a Quiz", elem_id="create-btn")
                    with gr.Column(elem_classes="card", min_width=300):
                        gr.Markdown(
                            "### ↗ Join a Game\n"
                            "Enter a game code and compete with friends."
                        )
                        home_join = gr.Button("Join a Game", elem_id="create-btn")

            # ----- EXPLORE -----
            with gr.Column(visible=False, elem_classes="view") as view_explore:
                gr.Markdown(
                    '<span class="eyebrow">// EXPLORE</span>\n## Pick a subject',
                    elem_classes=["title", "centered"],
                )
                with gr.Row():
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### ⚛ Physics\nMotion, forces, energy, waves and electricity.")
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### ⚗ Chemistry\nAtoms, reactions, bonding and the periodic table.")
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### 🧬 Biology\nCells, genetics, the body and ecosystems.")
                with gr.Row():
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### ∑ Mathematics\nAlgebra, calculus, statistics and geometry.")
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### 💻 Computer Science\nProgramming, data, networks and AI.")
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### 🌍 Earth & Space\nGeology, weather, planets and stars.")

            # ----- CREATE -----
            with gr.Column(visible=False, elem_classes="view") as view_create:
                gr.Markdown(
                    '<span class="eyebrow">// CREATE</span>\n## Build a quiz from your notes',
                    elem_classes=["title", "centered"],
                )
                with gr.Column(elem_classes="card"):
                    notes_file = gr.File(label="Upload notes (PDF or TXT)", file_types=[".pdf", ".txt"])
                    notes_box = gr.Textbox(
                        label="Or paste your notes",
                        lines=6,
                        placeholder="Paste a few paragraphs of your notes here",
                    )
                    count_slider = gr.Slider(5, 20, value=10, step=1, label="Number of questions")
                    seconds_slider = gr.Slider(10, 60, value=30, step=5, label="Seconds per question")
                    max_players = gr.Number(
                        value=30, minimum=1, maximum=200, precision=0, label="Max players"
                    )
                    generate_btn = gr.Button("✦  Generate questions", elem_id="generate-btn")
                    generate_msg = gr.Markdown("")

            # ----- JOIN -----
            with gr.Column(visible=False, elem_classes="view") as view_join:
                gr.Markdown(
                    '<span class="eyebrow">// JOIN</span>\n## Enter a game',
                    elem_classes=["title", "centered"],
                )
                with gr.Column(elem_classes="card") as join_form:
                    code_box = gr.Textbox(label="Game code", placeholder="e.g. 482915")
                    nick_box = gr.Textbox(label="Nickname")
                    join_btn = gr.Button("Join game  →", elem_id="join-game-btn")
                    join_msg = gr.Markdown("")

                # The quiz itself. Shown instead of the form while you are playing.
                with gr.Column(visible=False, elem_classes="quiz-card") as play_col:
                    play_q = gr.Markdown("")
                    play_clock = gr.Markdown("")
                    play_choice = gr.Radio([], show_label=False)
                    play_submit = gr.Button("Submit answer", elem_id="check-btn")
                    play_msg = gr.Markdown("")

            # ----- RANKS -----
            with gr.Column(visible=False, elem_classes="view") as view_board:
                gr.Markdown(
                    '<span class="eyebrow">// LEADERBOARD</span>\n## Top players',
                    elem_classes=["title", "centered"],
                )
                with gr.Column(elem_classes=["card", "board"]):
                    board_code = gr.Textbox(
                        label="Game code (leave empty for the overall ranking)",
                        placeholder="e.g. 482915",
                    )
                    board_btn = gr.Button("Refresh")
                    board_md = gr.Markdown("")

            view_columns = [view_home, view_explore, view_create, view_join, view_board]

        gr.Markdown(
            "© 2026 Knowva  ·  Built by DataBot  ·  Learn · Practise · Improve",
            elem_classes=["footer-note", "centered"],
        )

    # =========================================================
    # Wiring: what each button does
    # =========================================================
    nav_outputs = view_columns + nav_buttons
    stats_outputs = [xp_md, played_md, streak_md]
    play_outputs = [
        play_state, join_msg, join_form, play_col, play_q,
        play_choice, play_clock, play_msg, play_timer,
    ]

    for button, name in zip(nav_buttons, VIEWS):
        button.click(
            make_nav(name), inputs=None, outputs=nav_outputs, show_progress="hidden"
        )
    home_create.click(
        make_nav("create"), inputs=None, outputs=nav_outputs, show_progress="hidden"
    )
    home_join.click(
        make_nav("join"), inputs=None, outputs=nav_outputs, show_progress="hidden"
    )

    auth_outputs = (
        [user_state, auth_msg, auth_view, app_view, greeting]
        + nav_outputs
        + [login_pw, su_pw, su_confirm]
        + [session_token]
    )
    login_btn.click(
        log_in,
        inputs=[login_email, login_pw],
        outputs=auth_outputs,
        show_progress="hidden",
    ).then(refresh_stats, user_state, stats_outputs, show_progress="hidden")
    signup_btn.click(
        sign_up,
        inputs=[su_name, su_email, su_level, su_pw, su_confirm],
        outputs=auth_outputs,
        show_progress="hidden",
    ).then(refresh_stats, user_state, stats_outputs, show_progress="hidden")
    logout_btn.click(
        log_out,
        inputs=session_token,
        outputs=[user_state, auth_msg, auth_view, app_view, session_token],
        show_progress="hidden",
    )

    # Every time the page opens: check the browser's saved code
    demo.load(
        restore_session,
        inputs=session_token,
        outputs=[user_state, loading_view, auth_view, app_view, greeting] + nav_outputs,
        show_progress="hidden",
    ).then(refresh_stats, user_state, stats_outputs, show_progress="hidden")

    # Home: refresh the XP, quizzes played and streak whenever you open it
    nav_home.click(refresh_stats, user_state, stats_outputs, show_progress="hidden")

    # Create a quiz (one at a time, so the model doesn't run out of memory)
    generate_btn.click(
        generate_quiz,
        inputs=[user_state, notes_file, notes_box, count_slider, seconds_slider, max_players],
        outputs=generate_msg,
        show_progress="minimal",
        concurrency_limit=1,
    )

    # Join and play
    join_btn.click(
        join_game,
        inputs=[user_state, code_box, nick_box],
        outputs=play_outputs,
        show_progress="hidden",
    )
    play_submit.click(
        submit_answer,
        inputs=[user_state, play_state, play_choice],
        outputs=play_outputs,
        show_progress="hidden",
    ).then(refresh_stats, user_state, stats_outputs, show_progress="hidden")
    play_timer.tick(tick, inputs=play_state, outputs=play_clock, show_progress="hidden")

    # Ranks: refresh when opened, on the button, and every 5 seconds while it is open
    for button, name in zip(nav_buttons, VIEWS):
        button.click(timer_for(name), inputs=None, outputs=board_timer, show_progress="hidden")
    nav_board.click(render_board, board_code, board_md, show_progress="hidden")
    board_btn.click(render_board, board_code, board_md, show_progress="hidden")
    board_code.submit(render_board, board_code, board_md, show_progress="hidden")
    board_timer.tick(render_board, board_code, board_md, show_progress="hidden")


if __name__ == "__main__":
    demo.launch(**launch_options)