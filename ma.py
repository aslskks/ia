import ollama
client = ollama.Client(
    host="https://:11434"
)
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
print(generate_chat_title("hola"))