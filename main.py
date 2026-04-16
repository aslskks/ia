### Import
from flask import Flask, request, session, render_template, Response, redirect, url_for, jsonify, send_from_directory
from email.message import EmailMessage
from datetime import timedelta, datetime
from faster_whisper import WhisperModel
from flask_wtf import CSRFProtect
from passlib.hash import argon2
import json
import ollama
import secrets
import os
import uuid as uuid_lib
import requests
import smtplib
import ssl
import re
import subprocess
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hola")
csrf = CSRFProtect(app)
SECRET_KEY = "6LfmLmQsAAAAAJo-wFWCvhqx0nWbXKzf7swNUjK_"
SECRET_KEY_V2 = "6Lf4MWQsAAAAAKLe6xzCtdcWo5FmYxquFm0V5DKA"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = False  # True en producción
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
sender_email = "example901231@gmail.com"
ollama_model = 'llama3.1:8b'
password = os.getenv("GMAIL")
DB = 'database.db'
smtp_server = "smtp.gmail.com"
app.permanent_session_lifetime = timedelta(days=60)
port = 465
SYSTEM_PROMPT = open("system_prompt.txt", "r").read()
os.makedirs("voice", exist_ok=True)
model = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8",
    cpu_threads=8
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def open_conn():
    """Open a SQLite connection with row_factory and WAL mode enabled."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn, conn.cursor()


def _init_db():
    """Create tables once at startup, then close the connection."""
    conn, cursor = open_conn()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT 'New Chat',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT CHECK(role IN ('user','assistant')) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            user TEXT UNIQUE NOT NULL,
            code TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            fact TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        conn.commit()
    finally:
        cursor.close()
        conn.close()


_init_db()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def extract_python_blocks(text):
    pattern = r"```(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return [m.strip() for m in matches]


TAVILY_API_KEY = "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"


def perform_search(query: str, max_results: int = 5) -> str:
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results
            },
            timeout=5
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", []):
            title = r.get("title", "No title")
            url = r.get("url", "")
            content = r.get("content", "")
            results.append(f"- {title}\n  {content}\n  ({url})")

        if not results:
            return f"[No results found for: {query}]"

        return f"[Tavily search: '{query}']\n" + "\n\n".join(results)

    except requests.exceptions.Timeout:
        return f"[Search timed out for: {query}]"
    except requests.exceptions.ConnectionError:
        return f"[Search connection failed for: {query}]"
    except Exception as e:
        return f"[Search failed: {e}]"


def extract_search(text):
    match = re.search(r"\?\?\?(.*?)\?\?\?", text, re.DOTALL)
    if not match:
        return None

    q = match.group(1).strip()
    q = q.replace('"', '').replace("'", "")
    q = re.sub(
        r'^(búsqueda\s+por|buscar\s+por|buscar|búsqueda|search\s+for|search|lookup)\s+',
        '',
        q,
        flags=re.I
    )
    return q.strip()


def send_email(receiver, subject, title, button_text, link):
    text_body = f"""
{title}

This link will expire in 1 hour.

Open this link in your browser:
{link}

If you did not request this, ignore this email.
"""

    html_body = f"""
    <html>
    <body style="margin:0;padding:0;background:#f4f4f4;font-family:Helvetica,Arial,sans-serif;">
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td align="center">
                    <table width="600" cellpadding="0" cellspacing="0"
                        style="background:#ffffff;margin:40px auto;padding:40px;border-radius:10px;">
                        <tr>
                            <td align="center" style="font-size:24px;font-weight:bold;color:#000;">
                                {title}
                            </td>
                        </tr>
                        <tr>
                            <td align="center" style="font-size:16px;color:#333;line-height:1.6;padding:30px 0;">
                                This link will expire in 1 hour.<br><br>
                                <a href="{link}"
                                    style="background:#0ef;color:#000;padding:12px 24px;
                                            border-radius:6px;text-decoration:none;font-weight:bold;">
                                    {button_text}
                                </a><br><br>
                                If you did not request this, ignore this email.
                            </td>
                        </tr>
                        <tr>
                            <td align="center" style="font-size:12px;color:#888;">
                                © 2026 Your Company<br><br>
                                Or copy this link into your browser:<br>
                                <a href="{link}" style="color:#0bf;">{link}</a>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
        server.login(sender_email, os.getenv("GMAIL"))
        server.send_message(msg)


def generate_chat_title(message):
    try:
        response = ollama.chat(
            model=ollama_model,
            messages=[
                {
                    "role": "user",
                    "content": f"Create a very short title (max 5 words) for: {message}"
                }
            ]
        )
        return response["message"]["content"][:50]
    except Exception as e:
        print("TITLE ERROR:", e)
        return "New Chat"


def save_message(chat_id, role, content):
    """FIX: was missing commit() and connection close."""
    conn, cursor = open_conn()
    try:
        cursor.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?,?,?)",
            (chat_id, role, content)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

import sys


def install_package(pkg, cwd):
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=300
        )
        return True
    except Exception:
        return False


def extract_missing_module(output):
    match = re.search(r"No module named ['\"](.+?)['\"]", output)
    return match.group(1) if match else None


def _safe_sandbox_path(base: str, *parts: str) -> str:
    """
    FIX: Resolve the path and verify it stays inside `base`.
    Raises ValueError on path-traversal attempts.
    """
    base = os.path.realpath(base)
    target = os.path.realpath(os.path.join(base, *parts))
    if not target.startswith(base + os.sep) and target != base:
        raise ValueError(f"Path traversal detected: {target}")
    return target


def run_python_sandbox(code, uuid=None):
    if uuid is None:
        uuid = str(uuid_lib.uuid4())

    # Validate uuid looks like a UUID to avoid path-injection via chat_id
    if not re.fullmatch(r"[0-9a-f\-]{36}", uuid):
        raise ValueError("Invalid uuid")

    FILES_DIR = os.path.join(os.getcwd(), "files")
    sandbox_dir = _safe_sandbox_path(FILES_DIR, uuid)
    os.makedirs(sandbox_dir, exist_ok=True)

    script_path = os.path.join(sandbox_dir, "script.py")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)

    installed = set()
    output = ""
    for _ in range(5):
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=40,
                cwd=sandbox_dir,
                input=""
            )
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired as e:
            output = (e.stdout or "") + (e.stderr or "")
            output += "\n⏱️ Execution timed out after 40 seconds"
            break

        missing = extract_missing_module(output)
        if not missing:
            break
        if missing in installed:
            output += f"\n⚠️ Failed to install {missing}"
            break
        installed.add(missing)
        ok = install_package(missing, sandbox_dir)
        if not ok:
            output += f"\n⚠️ pip install failed for {missing}"
            break

    files = [f for f in os.listdir(sandbox_dir) if f != "script.py"]
    return {"output": output, "files": files, "uuid": uuid}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/me")
def me():
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    conn, cursor = open_conn()
    try:
        cursor.execute(
            "SELECT user, email FROM users WHERE id=?",
            (session["user_id"],)
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if row is None:
        return jsonify({"error": "user not found"}), 404

    return jsonify({"name": row["user"], "email": row["email"], "avatar": ""})


@app.route("/uuid")
def uuid_generate():
    return jsonify({"uuid": str(uuid_lib.uuid4())})


@app.route("/reset/<code>", methods=["GET", "POST"])
def reset(code):
    if request.method == "GET":
        conn, cursor = open_conn()
        try:
            cursor.execute("SELECT user, created_at FROM codes WHERE code = ?", (code,))
            rs = cursor.fetchone()
            if rs is None:
                return render_template("reset_invalid.html", error="The code is invalid or has already been used")

            user = rs["user"]
            # FIX: created_at comes back as a string from SQLite; parse it properly
            created_at_raw = rs["created_at"]
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except (TypeError, ValueError):
                return render_template("reset_invalid.html", error="Code has an invalid timestamp")

            if datetime.now() > created_at + timedelta(hours=1):
                cursor.execute("DELETE FROM codes WHERE user = ?", (user,))
                conn.commit()
                return render_template("reset_invalid.html", error="The code has already expired")

            return render_template("reset.html", code=code)
        except Exception as e:
            print(e)
            return render_template("reset_invalid.html", error=f"An error occurred {e}")
        finally:
            cursor.close()
            conn.close()

    # POST
    conn, cursor = open_conn()
    try:
        form_code = request.form.get("code")
        new_password = request.form.get("new_password")

        cursor.execute("SELECT user FROM codes WHERE code = ?", (form_code,))
        result = cursor.fetchone()
        if not result:
            return render_template("reset_invalid.html", error="The code does not exist or has already been used")

        user = result["user"]

        cursor.execute("SELECT password_hash, email FROM users WHERE user = ?", (user,))
        user_row = cursor.fetchone()
        if user_row is None:
            return render_template("reset_invalid.html", error="User not found")

        if argon2.verify(new_password, user_row["password_hash"]):
            return render_template("reset.html", code=form_code, error="The new password is the same as the old one")

        password_hash = argon2.hash(new_password)
        cursor.execute("DELETE FROM codes WHERE user = ?", (user,))
        cursor.execute("UPDATE users SET password_hash = ? WHERE user = ?", (password_hash, user))
        conn.commit()

        send_email(user_row["email"], "Password changed", "Password changed", "Dashboard", "http://127.0.0.1:5000/dashboard")
    finally:
        cursor.close()
        conn.close()

    return render_template("index.html", message="Password changed — please log in")


@app.route("/new_chat", methods=["POST"])
@csrf.exempt
def new_chat():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    chat_id = str(uuid_lib.uuid4())
    conn, cursor = open_conn()
    try:
        cursor.execute(
            "INSERT INTO chats (id, user_id, title) VALUES (?, ?, ?)",
            (chat_id, session["user_id"], "New Chat")
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {"chat_id": chat_id}


@app.route("/speech_to_text", methods=["POST"])
@csrf.exempt
def transcribe():
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    file = request.files.get("audio")
    if not file:
        return jsonify({"error": "no audio file"}), 400

    filename = os.path.join("voice", f"{uuid_lib.uuid4().hex}.wav")
    try:
        file.save(filename)
        segments, info = model.transcribe(filename)
        text = "".join(segment.text for segment in segments)
    finally:
        # FIX: clean up voice file after transcription to avoid disk fill-up
        if os.path.exists(filename):
            os.remove(filename)

    return jsonify({"text": text, "language": info.language})


@app.route("/")
@csrf.exempt
def index():
    if session.get("username") is None:
        return redirect(url_for("login"))
    if "messages" not in session:
        session["messages"] = []
    return render_template("chat.html")


# FIX: removed /select_user and /get_users — they expose all usernames and allow
# unauthenticated session hijacking. If a user-switcher is needed it must be
# protected behind admin authentication.


def create_chat(user_id):
    chat_id = str(uuid_lib.uuid4())
    conn, cursor = open_conn()
    try:
        cursor.execute(
            "INSERT INTO chats (id, user_id, title) VALUES (?,?,'New Chat')",
            (chat_id, user_id)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return chat_id


# FIX: /create_user previously used undefined `email` and `password` variables.
# Route now reads them from the request JSON.
@app.route("/create_user", methods=["POST"])
def create_user():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    new_email = data.get("email", "").strip()
    new_password = data.get("password", "")

    if not username or not new_email or not new_password:
        return {"error": "username, email and password are required"}, 400

    conn, cursor = open_conn()
    try:
        cursor.execute(
            "INSERT INTO users (user, email, password_hash) VALUES (?, ?, ?)",
            (username, new_email, argon2.hash(new_password))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return {"error": "Username or email already exists"}, 409
    finally:
        cursor.close()
        conn.close()

    return {"status": "ok"}


@app.route("/delete_all_chats", methods=["POST"])
@csrf.exempt
def delete_all_messages():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    user_id = session["user_id"]
    conn, cursor = open_conn()
    try:
        cursor.execute(
            """
            DELETE FROM messages
            WHERE chat_id IN (SELECT id FROM chats WHERE user_id=?)
            """,
            (user_id,)
        )
        cursor.execute("DELETE FROM chats WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return "ok"


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "GET":
        return render_template("forgot.html")

    conn, cursor = open_conn()
    try:
        receiver_email = request.form.get("email", "").strip()
        code = os.urandom(32).hex()

        cursor.execute("SELECT user FROM users WHERE email = ?", (receiver_email,))
        result = cursor.fetchone()

        if result:
            user = result["user"]
            cursor.execute("DELETE FROM codes WHERE user = ?", (user,))
            cursor.execute("INSERT INTO codes (user, code) VALUES (?, ?)", (user, code))
            conn.commit()
            send_email(
                receiver_email,
                "Reset your password",
                "Reset your password",
                "Change your password",
                f"http://127.0.0.1:5000/reset/{code}"
            )
    finally:
        cursor.close()
        conn.close()

    return render_template("forgot.html", message="If the email exists, instructions were sent")


@app.route("/messages/<chat_id>")
def get_messages(chat_id):
    if "user_id" not in session:
        return {"error": "unauthorized"}, 401

    user_id = session["user_id"]
    conn, cursor = open_conn()
    try:
        # FIX: verify the chat belongs to the requesting user
        cursor.execute(
            "SELECT id FROM chats WHERE id=? AND user_id=?",
            (chat_id, user_id)
        )
        if not cursor.fetchone():
            return {"error": "Forbidden"}, 403

        cursor.execute(
            "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id",
            (chat_id,)
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return jsonify([(r["role"], r["content"]) for r in rows])


@app.route("/download/<uuid>/<filename>")
def download_file(uuid, filename):
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    # FIX: validate both uuid and filename to prevent path traversal
    if not re.fullmatch(r"[0-9a-f\-]{36}", uuid):
        return {"error": "Invalid id"}, 400
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return {"error": "Invalid filename"}, 400

    FILES_DIR = os.path.join(os.getcwd(), "files")
    safe_dir = _safe_sandbox_path(FILES_DIR, uuid)
    return send_from_directory(safe_dir, filename, as_attachment=True)


@app.post("/run_block")
@csrf.exempt
def run_block():
    if "user_id" not in session:
        return {"error": "not logged"}, 401

    data = request.get_json(silent=True) or {}
    uuid = data.get("chat_id", "")
    code = data.get("code", "")

    if not code:
        return {"error": "empty"}, 400

    # Validate uuid before passing to sandbox
    if not re.fullmatch(r"[0-9a-f\-]{36}", uuid):
        return {"error": "invalid chat_id"}, 400

    result = run_python_sandbox(code, uuid)
    return result


@app.post("/delete-download")
@csrf.exempt
def delete_download():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    data = request.get_json(silent=True) or {}
    files = data.get("files", [])
    chat_uuid = data.get("chat_id", "")

    if not re.fullmatch(r"[0-9a-f\-]{36}", chat_uuid):
        return {"error": "invalid chat_id"}, 400

    FILES_DIR = os.path.join(os.getcwd(), "files")
    base_path = _safe_sandbox_path(FILES_DIR, chat_uuid)

    for file in files:
        if "/" in file or "\\" in file or file.startswith("."):
            continue  # skip suspicious filenames silently
        try:
            path = _safe_sandbox_path(base_path, file)
            if os.path.exists(path):
                os.remove(path)
        except ValueError:
            continue

    script_path = os.path.join(base_path, "script.py")
    if os.path.exists(script_path):
        os.remove(script_path)

    if os.path.isdir(base_path) and not os.listdir(base_path):
        os.rmdir(base_path)

    return {"ok": True}


@app.route("/chat", methods=["POST"])
@csrf.exempt
def chat():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    chat_id = data.get("chat_id")
    user_id = session["user_id"]

    if not user_message:
        return {"error": "empty message"}, 400

    conn, cursor = open_conn()
    try:
        if not chat_id:
            chat_id = str(uuid_lib.uuid4())
            cursor.execute(
                "INSERT INTO chats (id, user_id, title) VALUES (?,?,'New Chat')",
                (chat_id, user_id)
            )
            conn.commit()
        else:
            # FIX: verify the chat belongs to the requesting user
            cursor.execute(
                "SELECT id FROM chats WHERE id=? AND user_id=?",
                (chat_id, user_id)
            )
            if not cursor.fetchone():
                return {"error": "Forbidden"}, 403

        cursor.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?,'user',?)",
            (chat_id, user_message)
        )
        conn.commit()

        cursor.execute(
            "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id",
            (chat_id,)
        )
        rows = cursor.fetchall()
        messages = [{"role": row["role"], "content": row["content"]} for row in rows]
    finally:
        cursor.close()
        conn.close()

    def generate():
        full_reply = ""
        try:
            system_content = SYSTEM_PROMPT
            base_messages = [{"role": "system", "content": system_content}] + messages

            yield json.dumps({"token": "", "chat_id": chat_id}) + "\n"

            first_response = ollama.chat(
                model=ollama_model,
                messages=base_messages,
                stream=False
            )
            probe = first_response["message"]["content"]
            search_query = extract_search(probe)

            if search_query:
                yield json.dumps({"token": f"🔍 Searching: *{search_query}*…\n\n", "chat_id": chat_id}) + "\n"
                search_results = perform_search(search_query)

                augmented_messages = base_messages + [
                    {
                        "role": "system",
                        "content": (
                            f"The following are real-time web search results for the query '{search_query}'. "
                            f"Use them to answer the user. Do NOT emit ???...??? tags again.\n\n"
                            f"{search_results}"
                        )
                    }
                ]

                stream = ollama.chat(
                    model=ollama_model,
                    messages=augmented_messages,
                    stream=True
                )

                for chunk in stream:
                    token = chunk["message"]["content"]
                    if not token:
                        continue
                    full_reply += token
                    yield json.dumps({"token": token, "chat_id": chat_id}) + "\n"
            else:
                full_reply = probe
                yield json.dumps({"token": probe, "chat_id": chat_id}) + "\n"

        except GeneratorExit:
            return
        except Exception as e:
            print("STREAM ERROR:", e)
            yield json.dumps({"token": f"\n\n[Error: {e}]", "chat_id": chat_id}) + "\n"

        if full_reply.strip():
            conn3, cursor3 = open_conn()
            try:
                cursor3.execute(
                    "INSERT INTO messages (chat_id, role, content) VALUES (?,'assistant',?)",
                    (chat_id, full_reply)
                )
                conn3.commit()
                cursor3.execute("SELECT title FROM chats WHERE id=?", (chat_id,))
                row = cursor3.fetchone()
                if row and row["title"] == "New Chat":
                    try:
                        new_title = generate_chat_title(user_message[:200] + " " + full_reply[:200])
                        cursor3.execute("UPDATE chats SET title=? WHERE id=?", (new_title, chat_id))
                        conn3.commit()
                    except Exception as e:
                        print("TITLE ERROR:", e)
            finally:
                cursor3.close()
                conn3.close()

    return Response(generate(), mimetype="text/plain")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("username") is not None:
            return redirect(url_for("index"))
        return render_template("index.html")

    token_v3 = request.form.get("recaptcha_v3")
    if not token_v3:
        return render_template("index.html", error="Captcha requerido", show_captcha_v2=True)

    verify_v3 = requests.post(
        "https://www.google.com/recaptcha/api/siteverify",
        data={"secret": SECRET_KEY, "response": token_v3, "remoteip": request.remote_addr}
    ).json()

    if not verify_v3.get("success"):
        return render_template("index.html", error="Captcha inválido", show_captcha_v2=True)

    score = verify_v3.get("score", 0)
    if score < 0.5:
        token_v2 = request.form.get("g-recaptcha-response")
        if not token_v2:
            return render_template("index.html", error="Confirma que no eres un robot", show_captcha_v2=True)

        verify_v2 = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": SECRET_KEY_V2, "response": token_v2, "remoteip": request.remote_addr}
        ).json()

        if not verify_v2.get("success"):
            return render_template("index.html", error="Captcha incorrecto", show_captcha_v2=True)

    user = request.form.get("user", "").strip()
    pwd = request.form.get("password", "")
    remember = request.form.get("remember")

    conn, cursor = open_conn()
    try:
        cursor.execute("SELECT password_hash, id FROM users WHERE user=?", (user,))
        result = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not result or not argon2.verify(pwd, result["password_hash"]):
        return render_template("index.html", error="Invalid credentials")

    session["user_id"] = result["id"]
    session["username"] = user
    if remember:
        session.permanent = True

    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    message = request.args.get("message")

    if request.method == "GET":
        if session.get("username") is not None:
            return redirect(url_for("index"))
        return render_template("index.html", message=message)

    user = request.form.get("user", "").strip()
    pwd = request.form.get("password", "")
    email = request.form.get("email", "").strip()

    conn, cursor = open_conn()
    try:
        cursor.execute("SELECT 1 FROM users WHERE user = ?", (user,))
        if cursor.fetchone():
            return render_template("index.html", error="Username already exists")

        token_v3 = request.form.get("recaptcha_v3")
        if not token_v3:
            return render_template("index.html", error="Captcha requerido", show_captcha_v2=True)

        verify_v3 = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": SECRET_KEY, "response": token_v3, "remoteip": request.remote_addr}
        ).json()

        if not verify_v3.get("success"):
            return render_template("index.html", error="Captcha inválido", show_captcha_v2=True)

        score = verify_v3.get("score", 0)
        if score < 0.5:
            token_v2 = request.form.get("g-recaptcha-response")
            if not token_v2:
                return render_template("index.html", error="Confirma que no eres un robot", show_captcha_v2=True)

            verify_v2 = requests.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data={"secret": SECRET_KEY_V2, "response": token_v2, "remoteip": request.remote_addr}
            ).json()

            if not verify_v2.get("success"):
                return render_template("index.html", error="Captcha incorrecto", show_captcha_v2=True)

        password_hash = argon2.hash(pwd)
        cursor.execute(
            "INSERT INTO users (user, email, password_hash) VALUES (?, ?, ?)",
            (user, email, password_hash)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return render_template("index.html", error="Username or email already exists")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("index"))


@app.route("/delete_chat", methods=["POST"])
@csrf.exempt
def delete_chat():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    data = request.get_json(silent=True) or {}
    chat_id = data.get("chat_id")
    user_id = session["user_id"]

    conn, cursor = open_conn()
    try:
        # FIX: only delete chats that belong to the current user
        cursor.execute(
            "DELETE FROM chats WHERE id=? AND user_id=?",
            (chat_id, user_id)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {"status": "ok"}


@app.route("/rename_chat", methods=["POST"])
@csrf.exempt
def rename_chat():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    data = request.get_json(silent=True) or {}
    chat_id = data.get("chat_id")
    title = data.get("title", "").strip()
    user_id = session["user_id"]

    conn, cursor = open_conn()
    try:
        # FIX: only rename chats that belong to the current user
        cursor.execute(
            "UPDATE chats SET title=? WHERE id=? AND user_id=?",
            (title, chat_id, user_id)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {"status": "ok"}


@app.route("/get_chats")
@csrf.exempt
def get_chats():
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    user_id = session["user_id"]
    conn, cursor = open_conn()
    try:
        cursor.execute(
            "SELECT id, title FROM chats WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        )
        chats = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return {chat["id"]: {"title": chat["title"]} for chat in chats}


@app.route("/load_chat/<chat_id>")
def load_chat(chat_id):
    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    user_id = session["user_id"]
    conn, cursor = open_conn()
    try:
        cursor.execute(
            "SELECT id FROM chats WHERE id=? AND user_id=?",
            (chat_id, user_id)
        )
        if not cursor.fetchone():
            return {"error": "Unauthorized"}, 403

        cursor.execute(
            "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id",
            (chat_id,)
        )
        rows = cursor.fetchall()
    finally:
        # FIX: connection was never closed in the original
        cursor.close()
        conn.close()

    return {"messages": [(r["role"], r["content"]) for r in rows]}


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)