"""Visual style presets that control how Stage 3 (Visuals) produces media."""

DOCUMENTARY_PROMPT = (
    "Act as an expert documentary filmmaker. Take my script and break it down into a "
    "chronological two-column AV (Audio/Video) script. For every sentence or phrase of "
    "narration on the left, provide an optimized AI image prompt on the right. Include "
    "camera directions (e.g., slow cinematic pan, tight macro shot), lighting style "
    "(e.g., archival film scan, 1990s BBC look), and specific historical/technical "
    "details. Ensure no text, signs, or modern emblems appear in the prompts."
)

VISUAL_STYLES = [
    {
        "id": "stock",
        "name": "Stock / Creative Commons",
        "description": "Free YouTube Creative Commons clips and Wikimedia Commons images (no key needed).",
        "source": "stock",
        "needs_key": False,
    },
    {
        "id": "documentary",
        "name": "Documentary Style",
        "description": "AI stills crossfaded with Creative Commons clips/images — cinematic camera moves, archival 1990s BBC lighting, historical detail (needs OpenRouter key).",
        "source": "mixed",
        "needs_key": True,
        "system_prompt": DOCUMENTARY_PROMPT,
    },
]

DEFAULT_STYLE = "stock"


def get_style(style_id: str) -> dict:
    for s in VISUAL_STYLES:
        if s["id"] == style_id:
            return s
    for s in VISUAL_STYLES:
        if s["id"] == DEFAULT_STYLE:
            return s
    return VISUAL_STYLES[0]


def build_documentary_prompt(scene: dict) -> str:
    """Turn a scene into an optimized documentary image prompt.

    Follows the Documentary Style instructions: camera directions, archival
    lighting, period detail, and no text/signs/logos/modern emblems.
    """
    subject = (scene.get("visual") or scene.get("narration") or "").strip()
    narration = (scene.get("narration") or "").strip()

    prompt = (
        f"Documentary film still of {subject}. "
        "Slow cinematic camera movement (gentle push-in or pan), archival film scan, "
        "1990s BBC documentary lighting, natural practical light, shallow depth of field, "
        "period-accurate historical and technical detail."
    )
    if narration and narration != subject:
        prompt += f" Context: {narration[:300]}"
    prompt += " No text, no signs, no logos, no watermarks, no modern emblems or anachronisms."
    return prompt
