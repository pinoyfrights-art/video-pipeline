import re

ATTR_RE = re.compile(
    r"^(visual|image|video|sfx|music|voice|duration)\s*:\s*(.+)$", re.IGNORECASE
)


def parse_script(script: str):
    """Split a script into scenes.

    Blank lines separate scenes. Lines matching ``key: value`` set scene
    attributes (visual/image/video, sfx, music, voice, duration); every other
    line is narration text.
    """
    scenes = []
    blocks = [b.strip() for b in re.split(r"\n\s*\n", (script or "").strip())]
    idx = 0
    for block in blocks:
        if not block:
            continue
        narration_lines = []
        attrs = {}
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            m = ATTR_RE.match(line)
            if m:
                attrs[m.group(1).lower()] = m.group(2).strip()
            else:
                narration_lines.append(line)

        narration = " ".join(narration_lines).strip()
        if not narration and not attrs:
            continue

        idx += 1
        visual = attrs.get("visual") or attrs.get("image") or attrs.get("video") or ""
        if not visual and narration:
            visual = first_sentence(narration)

        scenes.append({
            "id": f"scene_{idx:02d}",
            "index": idx,
            "narration": narration,
            "visual": visual,
            "sfx": attrs.get("sfx", ""),
            "music": attrs.get("music", ""),
            "voice": attrs.get("voice", ""),
            "duration": parse_duration(attrs.get("duration", "")),
        })
    return scenes


def first_sentence(text: str) -> str:
    m = re.match(r"([^.!?]+[.!?])", text)
    return (m.group(1) if m else text).strip()


def parse_duration(s):
    if not s:
        return None
    s = s.strip().lower()
    try:
        if s.endswith("s"):
            return float(s[:-1])
        return float(s)
    except ValueError:
        return None
