import asyncio
import edge_tts
import os
import uuid
from langdetect import detect
from faster_whisper import WhisperModel
os.makedirs("voice", exist_ok=True)
VOICE_MAP = {
    "es": "es-MX-DaliaNeural",
    "en": "en-US-AriaNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "zh-cn": "zh-CN-XiaoxiaoNeural",
    "ar": "ar-SA-ZariyahNeural",
    "hi": "hi-IN-SwaraNeural"
}

def get_voice(text):
    try:
        lang = detect(text).lower()
    except:
        lang = "en"

    voice = VOICE_MAP.get(lang, "en-US-AriaNeural")

    print("Detected:", lang)
    print("Voice:", voice)

    return voice

async def speak(text):
    filename = f"voice/{uuid.uuid4().hex}.mp3"
    voice = get_voice(text)

    await edge_tts.Communicate(text, voice).save(filename)
def tts(text):
    asyncio.run(speak(text))
def stx():
    model = WhisperModel(
        "small",
        device="cpu",
        compute_type="int8",
        cpu_threads=8
    )

    segments, info = model.transcribe("mic.wav", language="es")

    print("Idioma:", info.language)

    for segment in segments:
        print(segment.text)
