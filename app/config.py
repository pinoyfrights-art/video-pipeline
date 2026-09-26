from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATIC_DIR = Path(__file__).resolve().parent / "static"

DEFAULT_SETTINGS = {
    "voice": "en-US-AriaNeural",
    "voice_rate": "+0%",
    "voice_pitch": "+0Hz",
    "resolution": "1920x1080",
    "fps": 30,
    "captions": True,
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
