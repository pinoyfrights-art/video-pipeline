import json

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, jobs, state
from .pipeline import (
    stage1_script,
    stage2_voiceover,
    stage3_visuals,
    stage4_audio,
    stage5_assembly,
    styles,
    voices,
)

app = FastAPI(title="Video Pipeline")
config.ensure_dirs()

SETTINGS_PATH = config.DATA_DIR / "settings.json"


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        merged = dict(config.DEFAULT_SETTINGS)
        merged.update(json.loads(SETTINGS_PATH.read_text()))
        return merged
    return dict(config.DEFAULT_SETTINGS)


def save_settings(s: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(s, indent=2))


class ScriptIn(BaseModel):
    script: str


class SettingsIn(BaseModel):
    settings: dict


class PreviewIn(BaseModel):
    voice: str
    text: str | None = None


# ---------------------------------------------------------------- health
@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- settings
@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.post("/api/settings")
def set_settings(body: SettingsIn):
    s = load_settings()
    s.update(body.settings)
    save_settings(s)
    return s


@app.get("/api/voices")
def get_voices():
    return voices.VOICES


@app.post("/api/voices/preview")
def voice_preview(body: PreviewIn):
    if not voices.is_known_voice(body.voice):
        raise HTTPException(400, "Unknown voice")
    return {"url": voices.preview_url(body.voice, body.text)}


@app.get("/api/styles")
def get_styles():
    return styles.VISUAL_STYLES


# ---------------------------------------------------------------- projects
@app.post("/api/projects")
def create_project():
    return state.new_project()


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    st = state.load_state(pid)
    if st is None:
        raise HTTPException(404, "Project not found")
    return st


@app.get("/api/projects")
def list_projects():
    return state.list_projects()


@app.delete("/api/projects")
def delete_all_projects():
    return {"deleted_count": state.delete_all_projects()}


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    if not state.delete_project(pid):
        raise HTTPException(404, "Project not found")
    return {"deleted": pid}


@app.post("/api/projects/{pid}/script")
def set_script(pid: str, body: ScriptIn):
    st = state.load_state(pid)
    if st is None:
        raise HTTPException(404, "Project not found")
    scenes = stage1_script.parse_script(body.script)
    st["script"] = body.script
    st["scenes"] = scenes
    st["stages"]["script"] = {"status": "done", "scenes": len(scenes)}
    for k in ["voiceover", "visuals", "audio", "assembly"]:
        st["stages"][k] = {"status": "pending"}
    state.save_state(pid, st)
    return st


# ---------------------------------------------------------------- jobs
@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    job = jobs.get_job(jid)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


# ---------------------------------------------------------------- stages
def _stage_context(pid: str, st: dict) -> dict:
    return {
        "pid": pid,
        "root": config.DATA_DIR,
        "dir": state.project_dir(pid),
        "scenes": st["scenes"],
        "settings": load_settings(),
        "music_media": st.get("music_media"),
        "visual_style": st.get("visual_style"),
    }


@app.post("/api/projects/{pid}/stages/{stage}/run")
def run_stage(pid: str, stage: str, style: str | None = None):
    st = state.load_state(pid)
    if st is None:
        raise HTTPException(404, "Project not found")
    ctx = _stage_context(pid, st)

    def work(log, progress):
        progress(5)
        ctx["logger"] = log
        ctx["progress"] = progress
        if stage == "voiceover":
            if not st["scenes"]:
                raise RuntimeError("No scenes yet — save & parse the script first (Stage 1).")
            result = stage2_voiceover.run_voiceover(ctx)
            st["stages"]["voiceover"] = {"status": "done", "result": result}
        elif stage == "visuals":
            if not st["scenes"]:
                raise RuntimeError("No scenes yet — save & parse the script first (Stage 1).")
            chosen = style or st.get("visual_style") or "stock"
            result = stage3_visuals.run_visuals(ctx, style=chosen)
            st["visual_style"] = chosen
            st["stages"]["visuals"] = {"status": "done", "result": result}
        elif stage == "audio":
            if not st["scenes"]:
                raise RuntimeError("No scenes yet — save & parse the script first (Stage 1).")
            result = stage4_audio.run_audio(ctx)
            st["stages"]["audio"] = {"status": "done", "result": result}
            st["music_media"] = result.get("music")
        elif stage == "assembly":
            if not st["scenes"]:
                raise RuntimeError("No scenes yet — save & parse the script first (Stage 1).")
            result = stage5_assembly.run_assembly(ctx)
            st["stages"]["assembly"] = {"status": "done", "result": result}
        else:
            raise RuntimeError(f"Stage '{stage}' is not implemented yet.")
        state.save_state(pid, st)
        return result

    jid = jobs.start_job(work)
    return {"job_id": jid}


# ---------------------------------------------------------------- static
app.mount("/media", StaticFiles(directory=str(config.DATA_DIR)), name="media")
app.mount("/", StaticFiles(directory=str(config.STATIC_DIR), html=True), name="static")
