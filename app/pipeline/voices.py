"""Curated edge-tts (Microsoft) neural voices for narration.

Each entry:
    id       — the ShortName edge-tts expects (e.g. "en-US-GuyNeural")
    name     — short friendly name
    gender   — "Female" | "Male"
    accent   — friendly region label (used for grouping/filtering)
    age      — "Adult" | "Young"  (edge-tts exposes no true "older" voice)
    persona  — one-line character description from the voice metadata
"""

import asyncio
import hashlib

import edge_tts

from .. import config

PREVIEW_TEXT = "Hello! This is how I'll sound narrating your video. I hope you like it."

VOICES = [
    # ---- United States ----
    {"id": "en-US-AriaNeural", "name": "Aria", "gender": "Female", "accent": "American", "age": "Adult", "persona": "Positive, confident"},
    {"id": "en-US-JennyNeural", "name": "Jenny", "gender": "Female", "accent": "American", "age": "Adult", "persona": "Friendly, considerate, warm"},
    {"id": "en-US-AvaNeural", "name": "Ava", "gender": "Female", "accent": "American", "age": "Adult", "persona": "Expressive, caring, pleasant"},
    {"id": "en-US-EmmaNeural", "name": "Emma", "gender": "Female", "accent": "American", "age": "Adult", "persona": "Cheerful, clear, conversational"},
    {"id": "en-US-MichelleNeural", "name": "Michelle", "gender": "Female", "accent": "American", "age": "Adult", "persona": "Friendly, pleasant"},
    {"id": "en-US-AnaNeural", "name": "Ana", "gender": "Female", "accent": "American", "age": "Young", "persona": "Cute, playful (child-like)"},
    {"id": "en-US-GuyNeural", "name": "Guy", "gender": "Male", "accent": "American", "age": "Adult", "persona": "Passionate, energetic"},
    {"id": "en-US-ChristopherNeural", "name": "Christopher", "gender": "Male", "accent": "American", "age": "Adult", "persona": "Reliable, authoritative"},
    {"id": "en-US-AndrewNeural", "name": "Andrew", "gender": "Male", "accent": "American", "age": "Adult", "persona": "Warm, confident, authentic"},
    {"id": "en-US-BrianNeural", "name": "Brian", "gender": "Male", "accent": "American", "age": "Adult", "persona": "Approachable, casual, sincere"},
    {"id": "en-US-EricNeural", "name": "Eric", "gender": "Male", "accent": "American", "age": "Adult", "persona": "Rational, measured"},
    {"id": "en-US-RogerNeural", "name": "Roger", "gender": "Male", "accent": "American", "age": "Adult", "persona": "Lively, upbeat"},
    {"id": "en-US-SteffanNeural", "name": "Steffan", "gender": "Male", "accent": "American", "age": "Adult", "persona": "Rational, measured"},

    # ---- United Kingdom ----
    {"id": "en-GB-LibbyNeural", "name": "Libby", "gender": "Female", "accent": "British", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia", "gender": "Female", "accent": "British", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-GB-MaisieNeural", "name": "Maisie", "gender": "Female", "accent": "British", "age": "Young", "persona": "Young girl (child-like)"},
    {"id": "en-GB-RyanNeural", "name": "Ryan", "gender": "Male", "accent": "British", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-GB-ThomasNeural", "name": "Thomas", "gender": "Male", "accent": "British", "age": "Adult", "persona": "Friendly, positive"},

    # ---- Australia ----
    {"id": "en-AU-NatashaNeural", "name": "Natasha", "gender": "Female", "accent": "Australian", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-AU-WilliamMultilingualNeural", "name": "William", "gender": "Male", "accent": "Australian", "age": "Adult", "persona": "Friendly, positive (multilingual)"},

    # ---- Canada ----
    {"id": "en-CA-ClaraNeural", "name": "Clara", "gender": "Female", "accent": "Canadian", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-CA-LiamNeural", "name": "Liam", "gender": "Male", "accent": "Canadian", "age": "Adult", "persona": "Friendly, positive"},

    # ---- Ireland ----
    {"id": "en-IE-EmilyNeural", "name": "Emily", "gender": "Female", "accent": "Irish", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-IE-ConnorNeural", "name": "Connor", "gender": "Male", "accent": "Irish", "age": "Adult", "persona": "Friendly, positive"},

    # ---- India ----
    {"id": "en-IN-NeerjaNeural", "name": "Neerja", "gender": "Female", "accent": "Indian", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-IN-NeerjaExpressiveNeural", "name": "Neerja (Expressive)", "gender": "Female", "accent": "Indian", "age": "Adult", "persona": "Friendly, positive (expressive)"},
    {"id": "en-IN-PrabhatNeural", "name": "Prabhat", "gender": "Male", "accent": "Indian", "age": "Adult", "persona": "Friendly, positive"},

    # ---- New Zealand ----
    {"id": "en-NZ-MollyNeural", "name": "Molly", "gender": "Female", "accent": "New Zealand", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-NZ-MitchellNeural", "name": "Mitchell", "gender": "Male", "accent": "New Zealand", "age": "Adult", "persona": "Friendly, positive"},

    # ---- South Africa ----
    {"id": "en-ZA-LeahNeural", "name": "Leah", "gender": "Female", "accent": "South African", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-ZA-LukeNeural", "name": "Luke", "gender": "Male", "accent": "South African", "age": "Adult", "persona": "Friendly, positive"},

    # ---- Hong Kong ----
    {"id": "en-HK-YanNeural", "name": "Yan", "gender": "Female", "accent": "Hong Kong", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-HK-SamNeural", "name": "Sam", "gender": "Male", "accent": "Hong Kong", "age": "Adult", "persona": "Friendly, positive"},

    # ---- Singapore ----
    {"id": "en-SG-LunaNeural", "name": "Luna", "gender": "Female", "accent": "Singaporean", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-SG-WayneNeural", "name": "Wayne", "gender": "Male", "accent": "Singaporean", "age": "Adult", "persona": "Friendly, positive"},

    # ---- Philippines ----
    {"id": "en-PH-RosaNeural", "name": "Rosa", "gender": "Female", "accent": "Filipino", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-PH-JamesNeural", "name": "James", "gender": "Male", "accent": "Filipino", "age": "Adult", "persona": "Friendly, positive"},

    # ---- Kenya ----
    {"id": "en-KE-AsiliaNeural", "name": "Asilia", "gender": "Female", "accent": "Kenyan", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-KE-ChilembaNeural", "name": "Chilemba", "gender": "Male", "accent": "Kenyan", "age": "Adult", "persona": "Friendly, positive"},

    # ---- Nigeria ----
    {"id": "en-NG-EzinneNeural", "name": "Ezinne", "gender": "Female", "accent": "Nigerian", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-NG-AbeoNeural", "name": "Abeo", "gender": "Male", "accent": "Nigerian", "age": "Adult", "persona": "Friendly, positive"},

    # ---- Tanzania ----
    {"id": "en-TZ-ImaniNeural", "name": "Imani", "gender": "Female", "accent": "Tanzanian", "age": "Adult", "persona": "Friendly, positive"},
    {"id": "en-TZ-ElimuNeural", "name": "Elimu", "gender": "Male", "accent": "Tanzanian", "age": "Adult", "persona": "Friendly, positive"},
]

_VOICE_IDS = {v["id"] for v in VOICES}


def is_known_voice(voice_id: str) -> bool:
    return voice_id in _VOICE_IDS


def preview_url(voice_id: str, text: str | None = None) -> str:
    """Synthesize (and cache) a short sample of a voice; return its /media URL."""
    sample = (text or "").strip() or PREVIEW_TEXT
    key = hashlib.sha1(f"{voice_id}\u0000{sample}".encode("utf-8")).hexdigest()[:16]
    out_dir = config.DATA_DIR / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{key}.mp3"

    if not out.exists():
        async def _gen():
            await edge_tts.Communicate(sample, voice_id).save(str(out))
        asyncio.run(_gen())

    return f"/media/previews/{key}.mp3"
