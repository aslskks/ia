from flask import Flask, request, session, render_template, jsonify, Response
import json
import ollama
import secrets
import os
import uuid
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))


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
- Always respond in the same language as the user.

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
```python
print("hello")
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

@app.route("/new_chat", methods=["POST"])
def new_chat():

    chat_id = str(uuid.uuid4())

    if "chats" not in session:
        session["chats"] = {}

    session["chats"][chat_id] = {
        "title": "New Chat",
        "messages": []
    }

    session["current_chat"] = chat_id

    return {"chat_id": chat_id}
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

    response = ollama.chat(
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
def index():

    if "messages" not in session:
        session["messages"] = []

    return render_template("chat.html")


@app.route("/chat", methods=["POST"])
def chat():

    data = request.json

    user_message = data["message"]
    chat_id = data.get("chat_id")

    if "chats" not in session:
        session["chats"] = {}

    chats = session["chats"]

    if not chat_id or chat_id not in chats:

        chat_id = str(uuid.uuid4())

        chats[chat_id] = {
            "title": "New Chat",
            "messages": []
        }

        session["current_chat"] = chat_id

    messages = chats[chat_id]["messages"]

    # save user message immediately
    messages.append({
        "role": "user",
        "content": user_message
    })

    session["chats"] = chats
    session.modified = True

    # PASS messages and chats INTO generator
    def generate(messages, chats, chat_id, user_message):

        full_reply = ""

        stream = ollama.chat(
            model="llama3.2",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            stream=True
        )

        for chunk in stream:

            if "message" not in chunk:
                continue

            token = chunk["message"]["content"]

            if not token:
                continue

            full_reply += token

            yield json.dumps({
                "token": token,
                "chat_id": chat_id
            }) + "\n"

        # save assistant reply
        messages.append({
            "role": "assistant",
            "content": full_reply
        })

        # generate title
        if chats[chat_id]["title"] == "New Chat":
            chats[chat_id]["title"] = generate_chat_title(user_message)

        session["chats"] = chats
        session.modified = True

    return Response(
        generate(messages, chats, chat_id, user_message),
        mimetype="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )



@app.route("/get_chats")
def get_chats():

    if "chats" not in session:
        return {}

    return session["chats"]
@app.route("/load_chat/<chat_id>")
def load_chat(chat_id):

    chats = session.get("chats", {})

    if chat_id not in chats:
        return {"messages": []}

    return {
        "messages": chats[chat_id]["messages"]
    }


@app.route("/reset")
def reset():

    session.clear()
    return jsonify({"status": "reset"})


if __name__ == "__main__":
    app.run(debug=True)
