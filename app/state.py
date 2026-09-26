import json
import shutil
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


def list_projects() -> list[dict]:
    """Return lightweight metadata for every saved project, newest first."""
    items = []
    if config.DATA_DIR.exists():
        for d in config.DATA_DIR.iterdir():
            if not d.is_dir():
                continue
            st = load_state(d.name)
            if st is None:
                continue
            items.append({
                "id": st.get("id", d.name),
                "created_at": st.get("created_at", 0),
                "script": st.get("script", ""),
                "scenes": len(st.get("scenes", [])),
                "stages": {k: v.get("status") for k, v in st.get("stages", {}).items()},
            })
    items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return items


def delete_project(pid: str) -> bool:
    """Remove a project folder and everything in it. Returns True if it existed."""
    d = project_dir(pid)
    if d.exists():
        shutil.rmtree(d)
        return True
    return False


def delete_all_projects() -> int:
    """Remove all project folders. Returns how many were removed."""
    removed = 0
    for p in list_projects():
        if delete_project(p["id"]):
            removed += 1
    return removed
