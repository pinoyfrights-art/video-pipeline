import shutil
import subprocess
import sys
from pathlib import Path


def ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def ytdlp() -> str:
    """Absolute path to yt-dlp (installed alongside the venv python)."""
    local = Path(sys.executable).parent / "yt-dlp"
    if local.exists():
        return str(local)
    return shutil.which("yt-dlp") or "yt-dlp"


def run(cmd, log=None):
    cmd = [str(c) for c in cmd]
    if log:
        log("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr[-3000:]}"
        )
    return proc


def probe_duration(path) -> float:
    proc = subprocess.run(
        [ffprobe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    out = proc.stdout.strip()
    if not out:
        raise RuntimeError(f"Could not probe duration of {path}")
    return float(out)


def probe_sample_rate(path) -> int:
    proc = subprocess.run(
        [ffprobe(), "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    out = proc.stdout.strip()
    return int(out) if out else 24000


def concat_audio(paths, out, gap: float = 0.4, log=None):
    """Concatenate audio files with a silence gap between each, writing an mp3."""
    if not paths:
        raise ValueError("No audio files to concatenate")
    tmp = Path(out).parent / "_concat"
    tmp.mkdir(parents=True, exist_ok=True)
    sr = probe_sample_rate(paths[0])

    wavs = []
    for i, p in enumerate(paths):
        w = tmp / f"s{i}.wav"
        run([ffmpeg(), "-y", "-i", str(p), "-ar", str(sr), "-ac", "1",
             "-c:a", "pcm_s16le", str(w)], log=log)
        wavs.append(w)

    silence = tmp / "silence.wav"
    run([ffmpeg(), "-y", "-f", "lavfi", "-i", f"anullsrc=r={sr}:cl=mono",
         "-t", str(gap), "-c:a", "pcm_s16le", str(silence)], log=log)

    lst = tmp / "list.txt"
    with open(lst, "w") as f:
        for w in wavs:
            f.write(f"file '{w}'\n")
            f.write(f"file '{silence}'\n")

    run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:a", "libmp3lame", "-b:a", "192k", str(out)], log=log)
    return out
