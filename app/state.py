import json
import time
import uuid
from pathlib import Path

from . import config

STAGES = ["script", "voiceover", "visuals", "audio", "assembly"]


def new_project_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def project_dir(pid: str) -> Path:
    return config.DATA_DIR / pid


def state_path(pid: str) -> Path:
    return project_dir(pid) / "state.json"


def load_state(pid: str):
    path = state_path(pid)
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_state(pid: str, state) -> None:
    d = project_dir(pid)
    d.mkdir(parents=True, exist_ok=True)
    state_path(pid).write_text(json.dumps(state, indent=2, default=str))


def new_project():
    pid = new_project_id()
    state = {
        "id": pid,
        "created_at": time.time(),
        "script": "",
        "scenes": [],
        "stages": {s: {"status": "pending"} for s in STAGES},
    }
    save_state(pid, state)
    return state
