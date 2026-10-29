import base64
import hashlib
import hmac
import inspect
import json
import math
import os
import re
import secrets
import time
from pathlib import Path

import gradio as gr

import db
import scoring

# ---------------------------------------------------------
# Logo: DataBot/assets/knowva-logo.png
# All accounts, quizzes and scores live in the database (db.py).
# The database address comes from the DATABASE_URL setting.
# ---------------------------------------------------------
BASE_DIR = Path(__file__).parent
LOGO_PATH = BASE_DIR / "assets" / "knowva-logo.png"
SESSION_DAYS = 30  # how long you stay logged in


def logo_as_text(path):
    if not path.exists():
        print(f"Logo not found at: {path}")
        return ""
    data = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{data}"


LOGO_DATA = logo_as_text(LOGO_PATH)

try:
    db.init_db()
except Exception as exc:
    print("\n⚠️  Could not connect to the database:", exc)
    print("   Set DATABASE_URL first, then start the app again.\n")
    raise

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------
# Passwords and "stay logged in"
# ---------------------------------------------------------
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 200_000
    ).hex()
    return salt, digest


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
    return {"name": record["name"], "email": record["email"]}


def end_session(token):
    if token:
        db.delete_session(_token_key(token))


# ---------------------------------------------------------
# Styling
# ---------------------------------------------------------
css = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap');

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
.gradio-container .block { background: transparent !important; border: none !important; box-shadow: none !important; }

#shell { width: 100%; max-width: 1100px; margin: 0 auto !important; padding: 20px 24px 50px; }

.title h1, .title h2, .title h3 { font-family: 'Space Grotesk', sans-serif !important; color: #301065 !important; letter-spacing: -1px; }
.centered, .centered * { text-align: center !important; }
.subtle p { color: #4D4660 !important; font-size: 16px; line-height: 1.7; }
.eyebrow { font-family: 'JetBrains Mono', monospace; font-size: 12px; letter-spacing: 2px; font-weight: 700; color: #6C3BFF !important; }
.view { margin-top: 36px; }

#auth-card {
    width: 100%; max-width: 470px; margin: 40px auto 0 !important;
    background: #E3D9FF !important; border: 1px solid #CDBDFF !important;
    border-radius: 24px !important; padding: 32px !important;
    box-shadow: 0 22px 60px rgba(48, 16, 101, 0.16);
}
button[role="tab"] { background: transparent !important; color: #4D4660 !important; border: none !important; border-bottom: 2px solid transparent !important; border-radius: 0 !important; }
button[role="tab"].selected, button[role="tab"][aria-selected="true"] { color: #6C3BFF !important; border-bottom: 2px solid #6C3BFF !important; }

.gradio-container input, .gradio-container textarea, .gradio-container select {
    background: #F3EFFF !important; color: #22212A !important;
    border: 1px solid #BBA4FF !important; border-radius: 10px !important;
}
.gradio-container input::placeholder, .gradio-container textarea::placeholder { color: #6B6280 !important; opacity: 1; }
.gradio-container label span, .gradio-container .block-title, .gradio-container [data-testid="block-info"] {
    font-family: 'JetBrains Mono', monospace !important; font-size: 12px !important; color: #301065 !important;
}

#topbar { align-items: center; }
#pill-col { align-items: center; }
.nav-pill {
    background: #301065; border-radius: 999px; padding: 8px 12px !important; gap: 6px !important;
    flex-wrap: nowrap !important; width: fit-content !important; margin: 0 auto;
    box-shadow: 0 14px 40px rgba(48, 16, 101, 0.3);
}
.nav-pill > * { flex: 0 0 auto !important; width: auto !important; min-width: 100px !important; }
.nav-pill button {
    background: transparent !important; color: #E9E0FF !important; border: none !important;
    box-shadow: none !important; border-radius: 999px !important; min-width: 100px !important;
    white-space: nowrap !important; padding: 12px 18px !important; font-size: 13px !important; letter-spacing: 0.3px;
}
.nav-pill button:hover { background: rgba(255, 255, 255, 0.1) !important; }
.nav-pill button.primary { background: #FFD76A !important; color: #301065 !important; }
#logout-btn { background: transparent !important; color: #301065 !important; border: 1px solid #BBA4FF !important; padding: 10px 18px !important; }

.gradio-container div.card, .gradio-container div.panel {
    background: #E3D9FF !important; border: 1px solid #CDBDFF !important;
    border-radius: 16px !important; padding: 24px !important; margin-top: 16px;
}
.gradio-container div.card { transition: transform 0.2s; }
.gradio-container div.card:hover { transform: translateY(-4px); }
.card h1, .card h2, .card h3, .panel h1, .panel h2, .panel h3 {
    font-family: 'Space Grotesk', sans-serif !important; color: #301065 !important; margin: 6px 0 !important;
}
.card p, .panel p { color: #3B3350 !important; line-height: 1.7; }
.stat h1 { font-size: 40px !important; }

.gradio-container div.quiz-card {
    background: #301065 !important; border-radius: 22px !important; padding: 28px !important;
    box-shadow: 0 22px 60px rgba(48, 16, 101, 0.28);
}
.quiz-card *, .banner * { color: #FFFFFF !important; }
.quiz-card .eyebrow { color: #BBA4FF !important; }
.quiz-card h3 { font-family: 'Space Grotesk', sans-serif !important; font-size: 21px !important; line-height: 1.4; }
.quiz-card label { background: rgba(255, 255, 255, 0.08) !important; border: 1px solid rgba(187, 164, 255, 0.4) !important; border-radius: 10px !important; }
.quiz-card strong { color: #FFD76A !important; }

.board table { width: 100%; border-collapse: collapse; }
.board th, .board td { padding: 12px 10px; text-align: left; border-bottom: 1px solid #CDBDFF; color: #301065 !important; }
.board th { font-family: 'JetBrains Mono', monospace; font-size: 12px; letter-spacing: 1px; }

#create-btn, #login-btn, #signup-btn, #generate-btn, #join-game-btn, #save-btn {
    background: #6C3BFF !important; color: white !important; border: none !important;
}
#check-btn { background: #FFD76A !important; color: #301065 !important; border: none !important; }
button { font-family: 'JetBrains Mono', monospace !important; border-radius: 10px !important; font-weight: 700 !important; padding: 14px 22px !important; }

.footer-note p { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #4D4660 !important; margin-top: 50px !important; }

#auth-card .wrap, .card .wrap { display: flex !important; flex-wrap: wrap; gap: 10px !important; background: transparent !important; }
#auth-card .wrap label, .card .wrap label {
    background: #F3EFFF !important; border: 1px solid #BBA4FF !important;
    border-radius: 10px !important; padding: 10px 18px !important; cursor: pointer;
}
#auth-card .wrap label span, .card .wrap label span { color: #301065 !important; font-family: 'IBM Plex Sans', sans-serif; font-size: 14px; }
#auth-card .wrap label.selected, .card .wrap label.selected { background: #6C3BFF !important; border-color: #6C3BFF !important; }
#auth-card .wrap label.selected span, .card .wrap label.selected span { color: #FFFFFF !important; }
#auth-card input[type="radio"], .card input[type="radio"] { accent-color: #FFD76A; }

.card button.center { background: #F3EFFF !important; border: 2px dashed #6C3BFF !important; border-radius: 14px !important; min-height: 200px; }
.card .wrap { color: #301065 !important; }
.card .wrap .or { color: #6C3BFF !important; }
.card [data-testid="block-label"] { background: #6C3BFF !important; color: #FFFFFF !important; }
.gradio-container input[type="range"] { accent-color: #6C3BFF !important; }
.card input[type="number"], .panel input[type="number"] {
    background: #F3EFFF !important; border: 1px solid #BBA4FF !important; color: #301065 !important;
}
.card .head, .panel .head { background: transparent !important; border: none !important; }

/* Editable question table */
.panel table, .panel [role="grid"], .panel .table-wrap { background: #F3EFFF !important; }
.panel table *, .panel [role="grid"] *, .panel .table-wrap * { color: #22212A !important; }

.meta-text, .meta-text-center, .progress-text { display: none !important; }

.toast-body { background: #301065 !important; border: 1px solid #BBA4FF !important; border-radius: 12px !important; }
.toast-body, .toast-body * { color: #FFFFFF !important; }

@media (max-width: 760px) {
    #shell { padding: 12px 12px 40px; }
    #topbar { flex-wrap: wrap !important; }
    .nav-pill { overflow-x: auto; max-width: 100%; justify-content: flex-start; }
    .nav-pill > *, .nav-pill button { min-width: 84px !important; padding: 10px 12px !important; font-size: 12px !important; }
    button { padding: 12px 16px !important; }
    #auth-card { padding: 22px !important; margin-top: 16px !important; }
    .quiz-card label { width: 100%; }
}
"""

# ---------------------------------------------------------
# Navigation
# ---------------------------------------------------------
VIEWS = ["home", "explore", "create", "join", "board"]


def go(view):
    shown = [gr.update(visible=(v == view)) for v in VIEWS]
    buttons = [gr.update(variant="primary" if v == view else "secondary") for v in VIEWS]
    return shown + buttons


def make_nav(view):
    def _go():
        return go(view)
    return _go


BLANK_ROW = ["", "", "", "", "", "A"]


def blank_rows():
    return [list(BLANK_ROW)]


def reset_forms():
    """Empty the Create page and the typed boxes when you leave a page."""
    return None, "", "", blank_rows(), "", "", None, "", "", ""


# ---------------------------------------------------------
# Login and sign up
# ---------------------------------------------------------
def greeting_text(user):
    first = user["name"].split()[0]
    return (
        '<span class="eyebrow">// WELCOME BACK</span>\n'
        f"## Hello, {first}.\n"
        "Ready to learn something today?"
    )


def _success(user):
    token = create_session(user["email"])
    return (
        [user, "", gr.update(visible=False), gr.update(visible=True), greeting_text(user)]
        + go("home")
        + ["", "", ""]
        + [token]
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
    return _success({"name": record["name"], "email": email})


def sign_up(name, email, password, confirm):
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
    db.create_user(email, name, "Secondary school", salt, digest)
    return _success({"name": name, "email": email})


def restore_session(token):
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
# Home numbers, daily challenge, leaderboard
# ---------------------------------------------------------
def refresh_stats(user):
    xp = played = streak = 0
    if user:
        try:
            s = db.user_stats(user["email"])
            xp, played, streak = s["xp"], s["played"], s["streak"]
        except Exception as exc:
            print("Could not load stats:", exc)
    return (
        f'<span class="eyebrow">TOTAL XP</span>\n# {xp}',
        f'<span class="eyebrow">QUIZZES PLAYED</span>\n# {played}',
        f'<span class="eyebrow">DAY STREAK</span>\n# {streak}',
    )


def check_answer(choice):
    if not choice:
        gr.Warning("Pick an answer first.")
        return "Pick an answer first."
    if choice.startswith("B"):
        gr.Info("Correct!")
        return "✓ Correct! Newton's second law is F = ma."
    gr.Warning("Not quite. Try again!")
    return "Not quite. Hint: think about what happens to acceleration when you push harder."


def board_md(rows):
    if not rows:
        return "*No scores yet.*"
    lines = ["| RANK | PLAYER | XP |", "|---|---|---|"]
    for i, r in enumerate(rows, 1):
        name = str(r["name"]).replace("|", "/")
        lines.append(f"| {i} | {name} | {int(r['xp'] or 0)} |")
    return "\n".join(lines)


def load_board(code):
    code = (code or "").strip()
    try:
        return board_md(db.leaderboard(code or None))
    except Exception as exc:
        print("Could not load leaderboard:", exc)
        return "*Could not load the leaderboard.*"


# ---------------------------------------------------------
# CREATE: read notes, generate questions, edit, save
# ---------------------------------------------------------
def generate_questions(text, count):
    """>>> PLUG THE AI MODEL IN HERE <<<
    Must return a list like:
      [{"question": "...", "options": ["a", "b", "c", "d"], "answer_index": 0}, ...]
    Until it is connected, this raises NotImplementedError and you type questions by hand.
    """
    raise NotImplementedError


def read_source(file, text, first, last):
    path = getattr(file, "name", file)
    parts = []
    if path:
        path = str(path)
        if path.lower().endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(path)
            total = len(reader.pages)
            first = max(1, int(first or 1))
            last = int(last or first + 9)
            last = min(total, max(last, first), first + 24)  # at most 25 pages
            pages = [(reader.pages[i].extract_text() or "") for i in range(first - 1, last)]
            parts.append("\n".join(pages))
        else:
            parts.append(Path(path).read_text(errors="ignore"))
    if (text or "").strip():
        parts.append(text.strip())
    return "\n".join(parts).strip()


def to_rows(df):
    if df is None:
        return []
    try:
        return df.fillna("").values.tolist()
    except AttributeError:
        return [list(r) for r in df]


def on_generate(file, text, first, last, count):
    try:
        source = read_source(file, text, first, last)
    except Exception as exc:
        gr.Warning(f"Could not read the file: {exc}")
        return gr.skip(), f"⚠️ Could not read the file: {exc}"
    if not source:
        gr.Warning("Upload your notes or type some text first.")
        return gr.skip(), "Upload your notes or type some text first."
    try:
        questions = generate_questions(source, int(count))
    except NotImplementedError:
        gr.Warning("The AI model is not connected yet. Type your questions in the table below.")
        return blank_rows(), "The AI model is not connected yet. Type your questions in the table below."
    except Exception as exc:
        gr.Warning(f"Generation failed: {exc}")
        return gr.skip(), f"⚠️ Generation failed: {exc}"
    rows = [[q["question"], *q["options"], "ABCD"[q["answer_index"]]] for q in questions]
    gr.Info(f"{len(rows)} questions ready. Edit anything you like, then save.")
    return rows, f"✓ {len(rows)} questions generated. Edit anything, then save below."


def on_add_row(df):
    rows = to_rows(df)
    rows.append(list(BLANK_ROW))
    return rows


def on_save(user, title, seconds, players, df):
    if not user:
        gr.Warning("Please log in first.")
        return "Please log in first."
    questions = []
    for r in to_rows(df):
        cells = [str(x).strip() for x in list(r)[:6]]
        cells += [""] * (6 - len(cells))
        q, a, b, c, d, ans = cells
        if not (q or a or b or c or d):
            continue  # blank row
        if not (q and a and b and c and d):
            gr.Warning("Every question needs the question text and all four options.")
            return "⚠️ Every question needs the question text and all four options."
        letter = ans.upper()[:1]
        if len(letter) != 1 or letter not in "ABCD":
            gr.Warning("The Answer column must be A, B, C or D.")
            return "⚠️ The Answer column must be A, B, C or D."
        questions.append({"question": q, "options": [a, b, c, d], "answer_index": "ABCD".index(letter)})
    if not questions:
        gr.Warning("Add at least one question first.")
        return "Add at least one question first."
    title = (title or "").strip() or "Untitled quiz"
    code = db.create_quiz(user["email"], title, int(seconds), int(players), questions)
    gr.Info(f"Quiz saved. Game code: {code}")
    return (
        f"### ✓ Quiz saved\n"
        f"Your game code is **{code}**\n\n"
        f"Share it with your friends. They open **Join**, enter the code and a nickname, and play."
    )


# ---------------------------------------------------------
# JOIN and PLAY
# outputs: state, join_col, play_col, result_col, q_head, q_text,
#          q_choice, time_label, timer, result_md, join_msg
# ---------------------------------------------------------
N_PLAY = 11


def _skips():
    return [gr.skip()] * N_PLAY


def _question_view(state):
    q = db.get_question(state["ids"][state["pos"]])
    opts = q["options"]
    if isinstance(opts, str):
        opts = json.loads(opts)
    choices = [(f"{'ABCD'[i]}.  {o}", i) for i, o in enumerate(opts)]
    state["t0"] = time.time()
    number = state["offset"] + state["pos"] + 1
    return [
        state,
        gr.update(visible=False), gr.update(visible=True), gr.update(visible=False),
        f'<span class="eyebrow">QUESTION {number} OF {state["total"]}</span>',
        f"### {q['question']}",
        gr.update(choices=choices, value=None),
        f"⏱ {state['limit']}s",
        gr.Timer(active=True),
        gr.skip(),
        "",
    ]


def _result_view(state):
    xp, right, _answered = db.player_score(state["code"], state["email"])
    rows = db.leaderboard(state["code"])
    md = (
        f"## Game over\n"
        f"**Your XP:** {xp}  ·  **Correct:** {right} of {state['total']}\n\n"
        + board_md(rows)
    )
    return [
        None,
        gr.update(visible=False), gr.update(visible=False), gr.update(visible=True),
        gr.skip(), gr.skip(), gr.skip(), gr.skip(),
        gr.Timer(active=False),
        md,
        "",
    ]


def _record(state, chosen):
    q = db.get_question(state["ids"][state["pos"]])
    used = time.time() - state["t0"]
    correct = chosen is not None and chosen == q["answer_index"]
    points = scoring.points_for(correct, used, state["limit"])
    db.save_attempt(state["code"], state["email"], q["id"], chosen, correct, round(used, 2), points)
    if chosen is None:
        gr.Warning("Time's up!")
    elif correct:
        gr.Info(f"Correct! +{points} XP")
    else:
        gr.Warning("Wrong answer.")
    state["pos"] += 1
    if state["pos"] >= len(state["ids"]):
        return _result_view(state)
    return _question_view(state)


def start_game(code, nickname, user):
    code = (code or "").strip()
    nickname = (nickname or "").strip()
    out = _skips()
    if not user:
        gr.Warning("Please log in first.")
        return out
    if not code or not nickname:
        gr.Warning("Enter a game code and a nickname.")
        out[10] = "Enter a game code and a nickname."
        return out
    ok, msg = db.join_quiz(code, user["email"], nickname)
    if not ok:
        gr.Warning(msg)
        out[10] = f"⚠️ {msg}"
        return out
    quiz = db.get_quiz(code)
    ids = db.question_ids(code)
    done = db.answered_ids(code, user["email"])
    remaining = [i for i in ids if i not in done]
    state = {
        "code": code, "email": user["email"], "ids": remaining, "pos": 0,
        "offset": len(ids) - len(remaining), "total": len(ids),
        "limit": int(quiz["seconds_per_question"]), "t0": time.time(),
    }
    if not remaining:
        return _result_view(state)
    return _question_view(state)


def submit_answer(choice, state):
    if not state:
        return _skips()
    if choice is None:
        gr.Warning("Pick an answer first.")
        return _skips()
    return _record(state, int(choice))


def tick(state):
    if not state:
        return _skips()
    remaining = state["limit"] - (time.time() - state["t0"])
    if remaining > 0:
        out = _skips()
        out[7] = f"⏱ {math.ceil(remaining)}s"
        return out
    return _record(state, None)  # time ran out


def back_to_join():
    out = _skips()
    out[0] = None
    out[1] = gr.update(visible=True)
    out[2] = gr.update(visible=False)
    out[3] = gr.update(visible=False)
    out[8] = gr.Timer(active=False)
    out[10] = ""
    return out


# ---------------------------------------------------------
# Version settings
# ---------------------------------------------------------
blocks_options = {"title": "Knowva | Learn Smarter. Play to Know More."}
launch_options = {
    "server_name": "0.0.0.0",
    "server_port": int(os.environ.get("PORT", 7860)),
    "share": os.environ.get("RENDER") is None,
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
    game_state = gr.State(None)
    session_token = gr.BrowserState(
        None,
        storage_key="knowva_session",
        secret=os.environ.get("KNOWVA_SECRET", "knowva-local-secret"),
    )

    with gr.Column(elem_id="shell"):

        loading_view = gr.Markdown(
            '<span class="eyebrow">LOADING...</span>',
            visible=True, elem_classes=["centered", "view"],
        )

        # ============ LOGIN / SIGN UP ============
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
                    su_pw = gr.Textbox(label="Password (8+ characters)", type="password")
                    su_confirm = gr.Textbox(label="Confirm password", type="password")
                    signup_btn = gr.Button("Create account  →", elem_id="signup-btn")
            auth_msg = gr.Markdown("", elem_classes="centered")

        # ============ THE APP ============
        with gr.Column(visible=False) as app_view:

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
                stat_outputs = [xp_md, played_md, streak_md]

                with gr.Row(equal_height=False):
                    with gr.Column(scale=1, min_width=300):
                        with gr.Column(elem_classes="card"):
                            gr.Markdown("### ✦ Create a Quiz\nTurn your notes or a PDF into practice questions.")
                            home_create = gr.Button("Create a Quiz", elem_id="create-btn")
                        with gr.Column(elem_classes="card"):
                            gr.Markdown("### ↗ Join a Game\nEnter a game code and compete with friends.")
                            home_join = gr.Button("Join a Game", elem_id="create-btn")
                    with gr.Column(scale=1, min_width=300, elem_classes="quiz-card"):
                        gr.Markdown('<span class="eyebrow">DAILY CHALLENGE</span>')
                        gr.Markdown("### Which law states that force equals mass times acceleration?")
                        answer = gr.Radio(
                            ["A. Newton's first law", "B. Newton's second law",
                             "C. Newton's third law", "D. Hooke's law"],
                            show_label=False,
                        )
                        check_btn = gr.Button("Check answer", elem_id="check-btn")
                        answer_msg = gr.Markdown("")

            # ----- EXPLORE -----
            with gr.Column(visible=False, elem_classes="view") as view_explore:
                gr.Markdown('<span class="eyebrow">// EXPLORE</span>\n## Pick a subject',
                            elem_classes=["title", "centered"])
                with gr.Row():
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### ⚛ Physics\nMotion, forces, energy, waves and electricity.")
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### ⚗ Chemistry\nAtoms, reactions, bonding and the periodic table.")
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### 🧬 Biology\nCells, genetics, the body and ecosystems.")
                with gr.Row():
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### ∑ Mathematics\nAlgebra, geometry, trigonometry and statistics.")
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### 💻 Computer Science\nProgramming, data, networks and AI.")
                    with gr.Column(elem_classes="card", min_width=240):
                        gr.Markdown("### 🌍 Earth & Space\nGeology, weather, planets and stars.")

            # ----- CREATE -----
            with gr.Column(visible=False, elem_classes="view") as view_create:
                gr.Markdown('<span class="eyebrow">// CREATE</span>\n## Build a quiz from your notes',
                            elem_classes=["title", "centered"])
                with gr.Column(elem_classes="card"):
                    notes_file = gr.File(label="Upload notes (PDF or TXT)", file_types=[".pdf", ".txt"])
                    with gr.Row():
                        first_page = gr.Number(value=1, precision=0, minimum=1, label="From page")
                        last_page = gr.Number(value=10, precision=0, minimum=1, label="To page (max 25 pages)")
                    notes_text = gr.Textbox(label="Or paste notes / type a topic", lines=3,
                                            placeholder="e.g. Newton's laws of motion")
                    count_slider = gr.Slider(5, 20, value=10, step=1, label="Number of questions")
                    generate_btn = gr.Button("✦  Generate questions", elem_id="generate-btn")
                    gen_msg = gr.Markdown("")

                with gr.Column(elem_classes="panel"):
                    gr.Markdown("### Your quiz\nEdit any cell. Write the right answer as A, B, C or D.")
                    quiz_title = gr.Textbox(label="Quiz title", placeholder="e.g. Forces and motion")
                    with gr.Row():
                        seconds_slider = gr.Slider(10, 60, value=20, step=5, label="Seconds per question")
                        players_slider = gr.Slider(2, 100, value=30, step=1, label="Maximum players")
                    questions_df = gr.Dataframe(
                        value=blank_rows(),
                        headers=["Question", "A", "B", "C", "D", "Answer (A-D)"],
                        datatype=["str"] * 6,
                        interactive=True,
                        wrap=True,
                        label="Questions",
                    )
                    add_row_btn = gr.Button("+ Add a question row", size="sm")
                    save_btn = gr.Button("Save quiz and get game code  →", elem_id="save-btn")
                    saved_msg = gr.Markdown("")

            # ----- JOIN / PLAY -----
            with gr.Column(visible=False, elem_classes="view") as view_join:
                gr.Markdown('<span class="eyebrow">// JOIN</span>\n## Enter a game',
                            elem_classes=["title", "centered"])

                with gr.Column(elem_classes="card") as join_col:
                    code_box = gr.Textbox(label="Game code", placeholder="e.g. 482915")
                    nick_box = gr.Textbox(label="Nickname")
                    join_btn = gr.Button("Join game  →", elem_id="join-game-btn")
                    join_msg = gr.Markdown("")

                with gr.Column(visible=False, elem_classes="quiz-card") as play_col:
                    q_head = gr.Markdown("")
                    q_text = gr.Markdown("")
                    q_choice = gr.Radio(choices=[], show_label=False)
                    time_label = gr.Markdown("")
                    submit_btn = gr.Button("Submit answer", elem_id="check-btn")

                with gr.Column(visible=False, elem_classes=["card", "board"]) as result_col:
                    result_md = gr.Markdown("")
                    back_btn = gr.Button("Play another game", elem_id="create-btn")

                timer = gr.Timer(1.0, active=False)

            # ----- RANKS -----
            with gr.Column(visible=False, elem_classes="view") as view_board:
                gr.Markdown('<span class="eyebrow">// LEADERBOARD</span>\n## Top players',
                            elem_classes=["title", "centered"])
                with gr.Column(elem_classes=["card", "board"]):
                    board_code = gr.Textbox(label="Game code (leave empty for all games)")
                    board_btn = gr.Button("Show leaderboard", elem_id="create-btn")
                    board_view = gr.Markdown("")

            view_columns = [view_home, view_explore, view_create, view_join, view_board]

        gr.Markdown(
            "© 2026 Knowva  ·  Built by DataBot  ·  Learn · Practise · Improve",
            elem_classes=["footer-note", "centered"],
        )

    # =========================================================
    # Wiring
    # =========================================================
    nav_outputs = view_columns + nav_buttons

    for button, name in zip(nav_buttons, VIEWS):
        event = button.click(make_nav(name), inputs=None, outputs=nav_outputs, show_progress="hidden")
        if name == "home":
            event.then(refresh_stats, inputs=user_state, outputs=stat_outputs, show_progress="hidden")
        if name == "board":
            event.then(load_board, inputs=board_code, outputs=board_view, show_progress="hidden")
    home_create.click(make_nav("create"), inputs=None, outputs=nav_outputs, show_progress="hidden")
    home_join.click(make_nav("join"), inputs=None, outputs=nav_outputs, show_progress="hidden")

    reset_outputs = [
        notes_file, notes_text, gen_msg, questions_df, saved_msg,
        quiz_title, answer, answer_msg, code_box, nick_box,
    ]
    for button in [nav_home, nav_explore, nav_join, nav_board, home_join, logout_btn]:
        button.click(reset_forms, inputs=None, outputs=reset_outputs, show_progress="hidden")

    auth_outputs = (
        [user_state, auth_msg, auth_view, app_view, greeting]
        + nav_outputs
        + [login_pw, su_pw, su_confirm]
        + [session_token]
    )
    login_btn.click(
        log_in, inputs=[login_email, login_pw], outputs=auth_outputs, show_progress="hidden",
    ).then(refresh_stats, inputs=user_state, outputs=stat_outputs, show_progress="hidden")
    signup_btn.click(
        sign_up, inputs=[su_name, su_email, su_pw, su_confirm], outputs=auth_outputs, show_progress="hidden",
    ).then(refresh_stats, inputs=user_state, outputs=stat_outputs, show_progress="hidden")
    logout_btn.click(
        log_out, inputs=session_token,
        outputs=[user_state, auth_msg, auth_view, app_view, session_token],
        show_progress="hidden",
    )

    demo.load(
        restore_session, inputs=session_token,
        outputs=[user_state, loading_view, auth_view, app_view, greeting] + nav_outputs,
        show_progress="hidden",
    ).then(refresh_stats, inputs=user_state, outputs=stat_outputs, show_progress="hidden")

    check_btn.click(check_answer, inputs=answer, outputs=answer_msg, show_progress="hidden")

    # Create
    generate_btn.click(
        on_generate,
        inputs=[notes_file, notes_text, first_page, last_page, count_slider],
        outputs=[questions_df, gen_msg],
        show_progress="full",
    )
    add_row_btn.click(on_add_row, inputs=questions_df, outputs=questions_df, show_progress="hidden")
    save_btn.click(
        on_save,
        inputs=[user_state, quiz_title, seconds_slider, players_slider, questions_df],
        outputs=saved_msg,
        show_progress="hidden",
    )

    # Join and play
    play_outputs = [
        game_state, join_col, play_col, result_col, q_head, q_text,
        q_choice, time_label, timer, result_md, join_msg,
    ]
    join_btn.click(start_game, inputs=[code_box, nick_box, user_state], outputs=play_outputs, show_progress="hidden")
    submit_btn.click(submit_answer, inputs=[q_choice, game_state], outputs=play_outputs, show_progress="hidden")
    timer.tick(tick, inputs=game_state, outputs=play_outputs, show_progress="hidden")
    back_btn.click(back_to_join, inputs=None, outputs=play_outputs, show_progress="hidden")

    # Ranks
    board_btn.click(load_board, inputs=board_code, outputs=board_view, show_progress="hidden")


if __name__ == "__main__":
    demo.launch(**launch_options)