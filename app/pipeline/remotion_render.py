"""Render the final video with Remotion (motion graphics, captions, transitions)."""
import json
import shutil
import subprocess
from pathlib import Path

from .. import config

COMPOSITION = "VideoPipeline"


def remotion_dir() -> Path:
    return config.ROOT / "remotion"


def is_available() -> bool:
    """Remotion is usable when node and its installed CLI are present."""
    if shutil.which("node") is None:
        return False
    return (remotion_dir() / "node_modules" / ".bin" / "remotion").exists()


def _rel(pid: str, path: str | None) -> str | None:
    """Return a media path relative to data/ (resolved via public/ symlink)."""
    if not path:
        return None
    return f"{pid}/{path}"


def build_input(ctx, scenes, durations, W, H, fps, documentary) -> dict:
    # Lazy import to avoid a circular import with stage5_assembly.
    from .stage5_assembly import LEAD_S, caption_text

    pid = ctx["pid"]
    settings = ctx.get("settings") or {}
    proj = ctx["dir"]
    captions = bool(settings.get("captions", True))

    out_scenes = []
    for scene, dur in zip(scenes, durations):
        vm = scene.get("visual_media") or {}
        vtype = vm.get("type")
        if vtype == "video" and vm.get("clip") and (proj / vm["clip"]).exists():
            visual = {"type": "video", "src": _rel(pid, vm["clip"])}
        elif vtype == "image" and vm.get("image") and (proj / vm["image"]).exists():
            visual = {"type": "image", "src": _rel(pid, vm["image"])}
        else:
            visual = {"type": "none", "src": ""}

        narration = _rel(pid, scene["audio"]) if scene.get("audio") and (proj / scene["audio"]).exists() else None
        sfx = None
        if scene.get("sfx_media") and scene["sfx_media"].get("file") and (proj / scene["sfx_media"]["file"]).exists():
            sfx = _rel(pid, scene["sfx_media"]["file"])

        out_scenes.append({
            "index": scene["index"],
            "duration": round(dur, 3),
            "visual": visual,
            "narration": narration,
            "lead": LEAD_S,
            "sfx": sfx,
            "caption": caption_text(scene) if captions else None,
        })

    music = None
    m = ctx.get("music_media") or {}
    if m.get("rel") and (ctx["dir"] / m["rel"]).exists():
        music = _rel(pid, m["rel"])

    return {
        "fps": fps,
        "width": W,
        "height": H,
        "documentary": documentary,
        "captions": captions,
        "music": music,
        "scenes": out_scenes,
    }


def render(ctx, scenes, durations, out_dir, W, H, fps, documentary, log, progress) -> Path:
    """Run the Remotion CLI and return the rendered final.mp4 path."""
    pid = ctx["pid"]
    rdir = remotion_dir()
    input_json = rdir / f"input_{pid}.json"
    input_json.write_text(
        json.dumps(build_input(ctx, scenes, durations, W, H, fps, documentary), indent=2),
        encoding="utf-8",
    )

    out = (out_dir / "final.mp4").resolve()
    if out.exists():
        out.unlink()

    bin_path = rdir / "node_modules" / ".bin" / "remotion"
    cmd = [str(bin_path), "render", "src/index.ts", COMPOSITION, str(out),
           "--props", str(input_json), "--public-dir", str(config.DATA_DIR.resolve()),
           "--overwrite"]
    log("$ " + " ".join(cmd))
    log("Rendering with Remotion (motion graphics + transitions)…")
    progress(50)

    proc = subprocess.run(cmd, cwd=str(rdir), capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-15:]
        raise RuntimeError(f"Remotion render failed ({proc.returncode}):\n" + "\n".join(tail))
    if not out.exists():
        raise RuntimeError("Remotion render finished but produced no output file")

    # surface the last "Rendered … / Encoded …" line for the log
    lines = (proc.stderr or proc.stdout or "").splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("Rendered ") or line.startswith("Encoded "):
            log(line)
            break

    progress(95)
    return out
