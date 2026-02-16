from flask import Flask, request, session, render_template, Response, copy_current_request_context, redirect, url_for, jsonify
import json
import ollama
import secrets
import os
import uuid
import mysql.connector as mysql
from flask_wtf import CSRFProtect
from passlib.hash import argon2
import requests
import smtplib
import ssl
from email.message import EmailMessage
import ssl
from datetime import timedelta, datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
csrf = CSRFProtect(app)
SECRET_KEY = os.getenv("SECRET_KEY")
SECRET_KEY_V2 = os.getenv("SECRET_KEY_V2")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = False  # True en producción
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
sender_email = "example901231@gmail.com"
password = os.getenv("GMAIL")
smtp_server = "smtp.gmail.com"
app.permanent_session_lifetime = timedelta(days=60)
port = 465
client = ollama.Client(
    host="http://127.0.0.1:11434"
)
SYSTEM_PROMPT = """
You are a highly reliable, expert-level AI assistant running locally.

PRIMARY DIRECTIVE:
Accuracy, correctness, and reliability always take priority over creativity, verbosity, or speculation.

MISSION:
Provide truthful, safe, correct, and practical responses. Optimize for real-world usefulness.

CORE PRINCIPLES:

HONESTY:
- Never hallucinate facts, APIs, libraries, or capabilities.
- If something is unknown or uncertain, explicitly say:
  "I don't know" or "I'm not sure".
- Do not guess.

ACCURACY:
- Prefer proven, real-world solutions.
- Do not invent functions, endpoints, or behaviors.
- Use only valid, existing syntax and libraries.

CONTEXT:
- Maintain full conversation context.
- Do not contradict previous correct statements.
- Ask for clarification if the request is ambiguous.

LANGUAGE:
- ALWAYS respond in the same language as the user.
- DONT respond in another lenguage except the user ask for.

CLARITY:
- Be concise but complete.
- Avoid unnecessary filler text.
- Prefer structured responses when useful.

REASONING POLICY:

- Think step-by-step internally.
- Verify assumptions before answering.
- Prioritize correctness over speed or creativity.
- Do not expose internal chain-of-thought.
- Provide only the final reasoning summary when needed.

CODE RESPONSE RULES (STRICT):

- ALL code MUST be inside triple backticks.
- ALWAYS specify the language.

Example:
```
print("hello")
```
NEVER:

Output code outside code blocks

Mix explanation inside code blocks

Leave code blocks unclosed

CODE QUALITY REQUIREMENTS:

Code MUST be:

Correct

Runnable

Complete

Secure

Production-quality

Code MUST:

Include all required imports

Follow best practices

Use clear structure

Avoid deprecated methods

Avoid insecure patterns

SECURITY POLICY:

Always prefer secure implementations.

Avoid vulnerabilities including:

SQL injection

XSS

Command injection

Insecure authentication

Unsafe deserialization

Never recommend insecure practices unless explicitly requested, and clearly label them as unsafe.

ERROR HANDLING POLICY:

If request is:

Ambiguous → Ask clarification

Impossible → Explain why clearly

Unknown → Say "I don't know"

Never fabricate solutions.

EXECUTION ENVIRONMENT:

Running locally via Ollama

No internet access unless explicitly provided

No external APIs unless defined by user

Only use information from:

System prompt

Conversation context

Built-in model knowledge

PERSONALITY:

Professional
Precise
Efficient
Calm
Honest
Highly competent
Predictable
BACKTICK SAFETY RULE:

To prevent unintended code block termination:

- Never output triple backticks (```) inside code blocks.
- If the user explicitly asks to output triple backticks (```), output double backticks (``) instead.
- If triple backticks are required semantically, replace them with double backticks (``).
- This rule overrides normal formatting rules.

Example:

User request:
write ```

Correct response:
``
"""

def open_conn():
    conn = mysql.connect(host="localhost", user="root", password="hola", database="chat")
    return conn, conn.cursor()
conn, cursor = open_conn()
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")
cursor.execute("""CREATE TABLE IF NOT EXISTS chats (
    id CHAR(36) PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) DEFAULT 'New Chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
""")
cursor.execute("""CREATE TABLE IF NOT EXISTS messages (

    id INT AUTO_INCREMENT PRIMARY KEY,

    chat_id CHAR(36) NOT NULL,

    role ENUM('user','assistant') NOT NULL,

    content TEXT NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE

);
""")
cursor.execute("""CREATE TABLE IF NOT EXISTS codes(
    user VARCHAR(50) UNIQUE NOT NULL,
    code VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
conn.commit()
cursor.close()
conn.close()
@app.route("/me")
def me():

    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    db, cursor = open_conn()
    cursor.execute(
        "SELECT user, email FROM users WHERE id=%s",
        (session["user_id"],)
    )
    row = cursor.fetchone()

    return jsonify({
        "name": row[0],
        "email": row[1],
        "avatar": ""
    })

@app.route("/reset/<code>", methods=["GET", "POST"])
def reset(code):
    conn, cursor = open_conn()

    if request.method == "GET":
        try:
            cursor.execute("SELECT user, created_at FROM codes WHERE code = %s", (code,))
            rs = cursor.fetchone()
            if rs is None:
                return render_template("reset_invalid.html", error="The code is invalid or has already been used")
            user, created_at = rs
            if created_at + timedelta(hours=1) < datetime.now():
                cursor.execute("DELETE FROM codes WHERE user = %s", (user,))
                conn.commit()
                cursor.close()
                conn.close()
                return render_template("reset_invalid.html", error="The code has already expired")
            if rs is None:
                return render_template("reset_invalid.html", error="The code is invalid or has already been used")
            return render_template("reset.html", code=code)
        except Exception as e:
            print(e)
            return render_template("reset_invalid.html", error=f"An error occurred {e}")
        finally:
            cursor.close()
            conn.close()
    conn, cursor = open_conn()
    code = request.form.get("code")
    new_password = request.form.get("new_password")
    # Validación de seguridad

    try:
        cursor.execute("SELECT user FROM codes WHERE code = %s", (code,))
        result = cursor.fetchone()
        user = result[0]
    except mysql.Error:
        return render_template("reset_invalid.html", error="The code does not exists or has already been used")
    except Exception as e:
        return render_template("reset_invalid.html", error="Code is invalid")

    cursor.execute("SELECT password_hash FROM users WHERE user = %s", (user,))
    old_hash = cursor.fetchone()
    if argon2.verify(new_password, old_hash[0]):
        return render_template("reset.html", code=code, error="The new password is the same as the old one")
    cursor.execute("DELETE FROM codes WHERE user = %s", (user,))
    password_hash = argon2.hash(new_password)
    cursor.execute("SELECT email FROM users WHERE user = %s", (user,))
    res = cursor.fetchone()
    send_email(res[0], "Password changed", "Password changed", "Dashboard", "http://127.0.0.1:5000/dashboard")
    cursor.execute("UPDATE users SET password_hash = %s WHERE user = %s", (password_hash, user))
    conn.commit()
    cursor.close()
    conn.close()
    return render_template("index.html", message="Password Changed now login")
@app.route("/new_chat", methods=["POST"])
@csrf.exempt
def new_chat():

    chat_id = str(uuid.uuid4())

    conn, cursor = open_conn()

    cursor.execute(
        "INSERT INTO chats (id, user_id, title) VALUES (%s, %s, %s)",
        (chat_id, session["user_id"], "New Chat")
    )

    conn.commit()
    cursor.close()
    conn.close()
    return {"chat_id": chat_id}
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

    # ✅ THIS IS THE IMPORTANT PART
    msg.set_content(text_body)              # plain text first
    msg.add_alternative(html_body, subtype="html")  # html second

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
        server.login(sender_email, os.getenv("GMAIL"))
        server.send_message(msg)
def generate_chat_title(first_message):

    TITLE_PROMPT = f"""
Generate a very short title (3–6 words max) for this conversation.

Rules:
- No quotes
- No punctuation at start or end
- No period
- Only the title

User message:
{first_message}
"""

    response = client.chat(
        model="llama3.2",
        messages=[
            {"role": "system", "content": "You generate short chat titles."},
            {"role": "user", "content": TITLE_PROMPT}
        ]
    )

    title = response["message"]["content"].strip()

    return title


def chat_with_ollama(messages):

    response = ollama.chat(
        model="llama3.2",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages
    )

    return response["message"]["content"]


@app.route("/")
@csrf.exempt
def index():
    if "user" not in session:
        return redirect(url_for("login"))
    if "messages" not in session:
        session["messages"] = []
    return render_template("chat.html")

@app.route("/select_user")
def select_user_page():
    return render_template("select_user.html")


@app.route("/get_users")
def get_users():
    db = mysql.connect(host="localhost", user="root", password="hola", database="chat")

    cursor = db.cursor()

    cursor.execute("SELECT user FROM users")

    users = [u[0] for u in cursor.fetchall()]

    return jsonify(users)



@app.route("/select_user", methods=["POST"])
def select_user_post():

    username = request.json["username"]

    session["user"] = username

    return "ok"
def create_chat(user_id):
    db = mysql.connect(host="localhost", user="root", password="hola", database="chat")
    chat_id = str(uuid.uuid4())

    cursor = db.cursor()

    cursor.execute(
        "INSERT INTO chats (id, user_id, title) VALUES (%s,%s,'New Chat')",
        (chat_id, user_id)
    )

    db.commit()

    return chat_id


@app.route("/create_user", methods=["POST"])
def create_user():
    db = mysql.connect(host="localhost", user="root", password="hola", database="chat")

    username = request.json["username"]

    cursor = db.cursor()

    cursor.execute(
        "INSERT IGNORE INTO users(user) VALUES(%s)",
        (username,)
    )

    db.commit()

    return "ok"


@app.route("/delete_all_messages", methods=["POST"])
def delete_all_messages():

    username = session["user"]
    db = mysql.connect(host="localhost", user="root", password="hola", database="chat")
    cursor = db.cursor()
    user_id = session.get("user_id")

    cursor.execute(
        """
        DELETE m FROM messages m
        JOIN chats c ON m.chat_id = c.id
        WHERE c.user_id=%s
        """,
        (user_id,)
    )

    cursor.execute(
        "DELETE FROM chats WHERE user=%s",
        (username,)
    )

    db.commit()

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
    receiver_email = request.form.get("email")
    code = os.urandom(32).hex()

    cursor.execute("SELECT user FROM users WHERE email = %s", (receiver_email,))
    result = cursor.fetchone()

    if result:
        user = result[0]
        cursor.execute("DELETE FROM codes WHERE user = %s", (user,))
        cursor.execute("INSERT INTO codes (user, code) VALUES (%s, %s)", (user, code))
        conn.commit()
        send_email(receiver_email, "Reset your password", "Reset your password", "Change your password", f"http://127.0.0.1:5000/reset/{code}")

    cursor.close()
    conn.close()

    return render_template("forgot.html", message="If the email exists, instructions were sent")

@app.route("/messages/<chat_id>")
def get_messages(chat_id):

    if "user_id" not in session:
        return {"error": "unauthorized"}, 401

    conn = mysql.connect(
        host="localhost",
        user="root",
        password="hola",
        database="chat"
    )

    cursor = conn.cursor(dictionary=True)  # 🔥 ESTA LINEA ES LA CLAVE

    cursor.execute("""
        SELECT role, content
        FROM messages
        WHERE chat_id=%s
        ORDER BY id
    """, (chat_id,))

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(rows)



@app.route("/chat", methods=["POST"])
@csrf.exempt
def chat():

    if "user_id" not in session:
        return {"error": "Not logged in"}, 401

    data = request.json
    user_message = data.get("message", "").strip()
    chat_id = data.get("chat_id")

    if not user_message:
        return {"error": "empty message"}, 400

    db = mysql.connect(
        host="localhost",
        user="root",
        password="hola",
        database="chat"
    )

    cursor = db.cursor(dictionary=True)

    # crear chat si no existe
    if not chat_id:

        chat_id = str(uuid.uuid4())

        cursor.execute(
            """
            INSERT INTO chats (id, user_id, title)
            VALUES (%s,%s,'New Chat')
            """,
            (chat_id, session["user_id"])
        )

        db.commit()

    # guardar mensaje usuario
    cursor.execute(
        """
        INSERT INTO messages (chat_id, role, content)
        VALUES (%s,'user',%s)
        """,
        (chat_id, user_message)
    )

    db.commit()

    # obtener historial
    cursor.execute(
        """
        SELECT role, content
        FROM messages
        WHERE chat_id=%s
        ORDER BY id
        """,
        (chat_id,)
    )

    messages = cursor.fetchall()
    conn.commit()
    cursor.close()
    conn.close()
    @copy_current_request_context
    def generate():

        full_reply = ""

        try:

            stream = ollama.chat(
                model="llama3.2",
                messages=[{"role":"system","content":SYSTEM_PROMPT}] + messages,
                stream=True
            )

            for chunk in stream:

                token = chunk["message"]["content"]

                if not token:
                    continue

                full_reply += token

                yield json.dumps({
                    "token": token,
                    "chat_id": chat_id
                }) + "\n"

        except Exception as e:

            print("STREAM ERROR:", e)

        # 🔥 GUARDAR FUERA DEL TRY
        # 🔥 GUARDAR RESPUESTA DEL ASSISTANT
        print("FINAL REPLY:", full_reply)

        if full_reply.strip():

            conn2, cursor2 = open_conn()

            # guardar respuesta
            cursor2.execute(
                """
                INSERT INTO messages (chat_id, role, content)
                VALUES (%s,'assistant',%s)
                """,
                (chat_id, full_reply)
            )

            conn2.commit()

            print("Assistant saved")

            # =========================
            # AUTO GENERAR TITULO
            # =========================

            cursor2.execute(
                "SELECT title FROM chats WHERE id=%s",
                (chat_id,)
            )

            current_title = cursor2.fetchone()[0]

            # solo si es nuevo
            if current_title == "New Chat":

                try:

                    new_title = generate_chat_title(user_message)

                    cursor2.execute(
                        "UPDATE chats SET title=%s WHERE id=%s",
                        (new_title, chat_id)
                    )

                    conn2.commit()

                    print("Title updated:", new_title)

                except Exception as e:

                    print("TITLE ERROR:", e)

            cursor2.close()
            conn2.close()






    return Response(generate(), mimetype="text/plain")




@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":

        if "user" in session:
            return redirect(url_for("index"))

        return render_template("index.html")


    # POST
    # =====================
    # VALIDAR reCAPTCHA v3
    # =====================

    token_v3 = request.form.get("recaptcha_v3")

    if not token_v3:
        return render_template(
            "index.html",
            error="Captcha requerido",
            show_captcha_v2=True
        )

    verify_v3 = requests.post(
        "https://www.google.com/recaptcha/api/siteverify",
        data={
            "secret": SECRET_KEY,
            "response": token_v3,
            "remoteip": request.remote_addr
        }
    ).json()

    # FALLÓ completamente
    if not verify_v3.get("success"):
        return render_template(
            "index.html",
            error="Captcha inválido",
            show_captcha_v2=True
        )

    score = verify_v3.get("score", 0)

    # =====================
    # SCORE BAJO → FORZAR v2
    # =====================

    if score < 0.5:

        token_v2 = request.form.get("g-recaptcha-response")

        if not token_v2:
            return render_template(
                "index.html",
                error="Confirma que no eres un robot",
                show_captcha_v2=True
            )

        verify_v2 = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": SECRET_KEY_V2,
                "response": token_v2,
                "remoteip": request.remote_addr
            }
        ).json()

        if not verify_v2.get("success"):
            return render_template(
                "index.html",
                error="Captcha incorrecto",
                show_captcha_v2=True
            )


    # login
    conn, cursor = open_conn()

    user = request.form.get("user")
    password = request.form.get("password")
    remember = request.form.get("remember")

    cursor.execute(
        "SELECT password_hash, id FROM users WHERE user=%s",
        (user,)
    )
    result = cursor.fetchone()

    if not result:
        return render_template("index.html", error="Invalid credentials")
    password_hash, id = result
    if argon2.verify(password, password_hash):
        session["user_id"] = id
        session["user"] = user
        if remember:
            session.permanent = True

        return redirect(url_for("index"))

    return render_template("index.html", error="Invalid credentials")

@app.route("/register", methods=["GET", "POST"])
def register():
    message = request.args.get("message")

    if request.method == "GET":
        if "user" in session:
            return redirect(url_for("dashboard"))
        return render_template("index.html", message=message)

    conn, cursor = open_conn()

    user = request.form.get("user")
    password = request.form.get("password")
    email = request.form.get("email")

    cursor.execute("SELECT 1 FROM users WHERE user = %s", (user,))
    if cursor.fetchone():
        return render_template("index.html", error="Username already exists")
    # =====================
    # VALIDAR reCAPTCHA v3
    # =====================

    token_v3 = request.form.get("recaptcha_v3")

    if not token_v3:
        return render_template(
            "index.html",
            error="Captcha requerido",
            show_captcha_v2=True
        )

    verify_v3 = requests.post(
        "https://www.google.com/recaptcha/api/siteverify",
        data={
            "secret": SECRET_KEY,
            "response": token_v3,
            "remoteip": request.remote_addr
        }
    ).json()

    # FALLÓ completamente
    if not verify_v3.get("success"):
        return render_template(
            "index.html",
            error="Captcha inválido",
            show_captcha_v2=True
        )

    score = verify_v3.get("score", 0)

    # =====================
    # SCORE BAJO → FORZAR v2
    # =====================

    if score < 0.5:

        token_v2 = request.form.get("g-recaptcha-response")

        if not token_v2:
            return render_template(
                "index.html",
                error="Confirma que no eres un robot",
                show_captcha_v2=True
            )

        verify_v2 = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": SECRET_KEY_V2,
                "response": token_v2,
                "remoteip": request.remote_addr
            }
        ).json()

        if not verify_v2.get("success"):
            return render_template(
                "index.html",
                error="Captcha incorrecto",
                show_captcha_v2=True
            )

    # =====================
    # Crear usuario
    # =====================
    password_hash = argon2.hash(password)
    cursor.execute(
        "INSERT INTO users (user, email, password_hash) VALUES (%s, %s, %s)",
        (user, email, password_hash)
    )

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for("index"))
@app.route("/delete_chat", methods=["POST"])
@csrf.exempt
def delete_chat():

    data = request.json
    db = mysql.connect(host='localhost', user="root", password="hola", database="chat")
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM chats WHERE id=%s",
        (data["chat_id"],)
    )

    db.commit()

    return {"status":"ok"}

@app.route("/rename_chat", methods=["POST"])
@csrf.exempt
def rename_chat():

    data = request.json
    db = mysql.connect(host='localhost', user="root", password="hola", database="chat")
    cursor = db.cursor()

    cursor.execute(
        "UPDATE chats SET title=%s WHERE id=%s",
        (data["title"], data["chat_id"])
    )

    db.commit()

    return {"status":"ok"}
def save_message(chat_id, role, content):
    db = mysql.connect(host="localhost", user="root", password="hola", database="chat")

    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO messages (chat_id, role, content)
        VALUES (%s,%s,%s)
        """,
        (chat_id, role, content)
    )

    db.commit()

@app.route("/get_chats")
def get_chats():
    db = mysql.connect(host="localhost", user="root", password="hola", database="chat")

    user_id = session["user_id"]

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id, title
        FROM chats
        WHERE user_id=%s
        ORDER BY created_at DESC
        """,
        (user_id,)
    )

    chats = cursor.fetchall()

    return {
        chat["id"]: {
            "title": chat["title"]
        }
        for chat in chats
    }

@app.route("/load_chat/<chat_id>")
def load_chat(chat_id):
    db = mysql.connect(host="localhost", user="root", password="hola", database="chat")

    user_id = session["user_id"]

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT id FROM chats
        WHERE id=%s AND user_id=%s
        """,
        (chat_id, user_id)
    )

    if not cursor.fetchone():
        return {"error":"Unauthorized"}, 403


    cursor.execute(
        """
        SELECT role, content
        FROM messages
        WHERE chat_id=%s
        ORDER BY id
        """,
        (chat_id,)
    )

    return {
        "messages": cursor.fetchall()
    }


if __name__ == "__main__":
    app.run(debug=True,)

