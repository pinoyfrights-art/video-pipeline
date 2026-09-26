import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from .utils import ffmpeg, probe_duration, run, ytdlp

YT_BASE_ARGS = [
    "--js-runtimes", "node",
    "--no-warnings",
]
YT_FORMAT = "bv*[height<=720][vcodec^=avc1][protocol^=https]+ba[protocol^=https]/b[height<=720][protocol^=https]/b"
UA = "VideoPipeline/1.0 (+https://example.net/video-pipeline; contact: pipeline@example.net)"


def run_visuals(ctx):
    """Find/download a visual (YouTube CC clip or Wikimedia image) per scene.

    ctx keys: pid, root, dir, scenes, settings, logger, progress.
    """
    log = ctx["logger"]
    progress = ctx.get("progress", lambda p: None)
    scenes = ctx["scenes"]
    out_dir = ctx["dir"] / "stage3_visuals"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    total = max(len(scenes), 1)
    for i, scene in enumerate(scenes):
        progress(5 + int(88 * i / total))
        log(f"[scene {scene['index']}] visual query: '{scene.get('visual') or '(none)'}'")
        item = acquire_visual(ctx, scene, out_dir, log)
        scene["visual_media"] = {
            k: v for k, v in item.items()
            if k in ("type", "clip", "image", "thumb", "source", "source_title",
                     "source_url", "license", "author", "duration", "reason")
        }
        # keep relative paths in state, not /media URLs
        for key in ("clip", "image", "thumb"):
            if scene["visual_media"].get(key) and str(scene["visual_media"][key]).startswith("/media/"):
                scene["visual_media"][key] = scene["visual_media"][key].split("/", 3)[-1]
        results.append(item)
    progress(95)
    n_ok = sum(1 for r in results if r.get("type") in ("video", "image"))
    log(f"Visuals complete: {n_ok}/{len(results)} scene(s) have media")
    return {"scenes": results, "count": n_ok, "total": len(results)}


def acquire_visual(ctx, scene, out_dir, log):
    query = (scene.get("visual") or "").strip()
    sdir = out_dir / scene["id"]
    if sdir.exists():
        for f in sdir.iterdir():
            if f.is_file():
                f.unlink()
    sdir.mkdir(parents=True, exist_ok=True)

    if not query:
        return {"scene": scene["id"], "type": "none", "reason": "no visual keywords"}

    clip_len = max(4.0, min(120.0, scene_seconds(scene) + 2.0))

    attempts = [query]
    if "creative commons" not in query.lower():
        attempts.append(query + " creative commons")

    for q in attempts:
        try:
            item = try_youtube(ctx, scene, sdir, q, clip_len, log)
            if item:
                return item
        except Exception as e:  # noqa: BLE001 - try next query / fallback
            log(f"  YouTube attempt failed: {e}")

    log("  no Creative Commons video found — falling back to Wikimedia Commons image")
    try:
        return try_wikimedia(ctx, scene, sdir, query, log)
    except Exception as e:  # noqa: BLE001
        log(f"  Wikimedia fallback failed: {e}")
        return {"scene": scene["id"], "type": "none", "reason": str(e)}


def try_youtube(ctx, scene, sdir, query, clip_len, log):
    pid = ctx["pid"]
    cmd = [ytdlp(), *YT_BASE_ARGS,
           "--match-filter", "license~='(?i)creative commons'",
           "--max-downloads", "1",
           "--download-sections", f"*0-{clip_len:.1f}",
           "-f", YT_FORMAT,
           "--merge-output-format", "mp4",
           "--write-thumbnail", "--write-info-json", "--no-write-playlist-metafiles",
           "-o", str(sdir / "%(id)s.%(ext)s"),
           f"ytsearch8:{query}"]
    log(f"  searching YouTube CC: '{query}'")
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)

    src_mp4s = sorted(sdir.glob("*.mp4"))
    if src_mp4s:
        # exit 101 == --max-downloads reached (expected success); clip is present
        if proc.returncode not in (0, 101):
            log(f"  note: yt-dlp exited {proc.returncode} but clip downloaded fine")
    else:
        if proc.returncode not in (0, 101):
            log(f"  yt-dlp error ({proc.returncode}): {clean_stderr(proc.stderr)}")
        return None
    src_mp4 = src_mp4s[0]

    clip = sdir / "clip.mp4"
    log(f"  normalizing clip (h264/aac)…")
    run([ffmpeg(), "-y", "-i", str(src_mp4), "-t", f"{clip_len:.2f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ac", "2",
         "-movflags", "+faststart", str(clip)], log=log)

    thumb = sdir / "thumb.jpg"
    make_thumbnail(sdir, src_mp4, thumb, log)

    info = find_info_json(sdir)
    meta = read_youtube_meta(info) if info else {}
    dur = round(probe_duration(clip), 2)
    cleanup(sdir, keep={clip.name, thumb.name, "source.json"})
    write_source(sdir, meta)

    return {
        "scene": scene["id"], "index": scene["index"], "type": "video",
        "clip": f"/media/{pid}/stage3_visuals/{scene['id']}/clip.mp4",
        "image": f"/media/{pid}/stage3_visuals/{scene['id']}/thumb.jpg",
        "duration": dur,
        **meta,
    }


def try_wikimedia(ctx, scene, sdir, query, log):
    pid = ctx["pid"]
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": 8,
        "prop": "imageinfo", "iiprop": "url|extmetadata|mediatype",
        "iiurlwidth": 1600, "format": "json",
    }
    url = api + "?" + urllib.parse.urlencode(params)
    log(f"  searching Wikimedia Commons: '{query}'")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())

    pages = (data.get("query") or {}).get("pages") or {}
    for _, page in pages.items():
        ii = (page.get("imageinfo") or [None])[0]
        if not ii:
            continue
        if ii.get("mediatype") not in ("BITMAP", "DRAWING"):
            continue
        thumburl = ii.get("thumburl") or ii.get("url")
        if not thumburl:
            continue
        ext = Path(urllib.parse.urlparse(thumburl).path).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff"):
            continue
        em = ii.get("extmetadata") or {}
        meta = {
            "source": "Wikimedia Commons",
            "source_title": (page.get("title") or "").replace("File:", "", 1),
            "source_url": ii.get("descriptionurl", ""),
            "license": strip_html(em.get("LicenseShortName", {}).get("value", "")),
            "author": strip_html(em.get("Artist", {}).get("value", "")),
        }
        log(f"  downloading image: {meta['source_title']}")
        req2 = urllib.request.Request(thumburl, headers={"User-Agent": UA})
        with urllib.request.urlopen(req2, timeout=60) as r:
            raw = r.read()
        img = sdir / f"image{ext}"
        img.write_bytes(raw)
        thumb = sdir / "thumb.jpg"
        run([ffmpeg(), "-y", "-i", str(img), "-frames:v", "1", "-q:v", "3", str(thumb)], log=log)
        cleanup(sdir, keep={img.name, thumb.name, "source.json"})
        write_source(sdir, meta)
        return {
            "scene": scene["id"], "index": scene["index"], "type": "image",
            "image": f"/media/{pid}/stage3_visuals/{scene['id']}/image{ext}",
            "thumb": f"/media/{pid}/stage3_visuals/{scene['id']}/thumb.jpg",
            **meta,
        }
    return {"scene": scene["id"], "type": "none", "reason": "no image found on Wikimedia Commons"}


# ---------------------------------------------------------------- helpers
def scene_seconds(scene) -> float:
    if scene.get("audio_duration"):
        return float(scene["audio_duration"])
    if scene.get("duration"):
        return float(scene["duration"])
    words = len((scene.get("narration") or "").split())
    if words:
        return max(2.0, min(40.0, words * 0.42))
    return 5.0


def make_thumbnail(sdir, src_mp4, dst, log):
    thumb_src = None
    for ext in ("webp", "jpg", "jpeg", "png"):
        candidates = sorted(sdir.glob(f"*.{ext}"))
        if candidates:
            thumb_src = candidates[0]
            break
    if thumb_src:
        run([ffmpeg(), "-y", "-i", str(thumb_src), "-vf", "scale=640:-2",
             "-frames:v", "1", "-q:v", "3", str(dst)], log=log)
    else:
        run([ffmpeg(), "-y", "-i", str(src_mp4), "-ss", "0.5", "-frames:v", "1",
             "-vf", "scale=640:-2", "-q:v", "3", str(dst)], log=log)


def find_info_json(sdir):
    candidates = sorted(sdir.glob("*.info.json"))
    return candidates[0] if candidates else None


def read_youtube_meta(info_path) -> dict:
    d = json.loads(info_path.read_text())
    return {
        "source": "YouTube",
        "source_title": d.get("title", ""),
        "source_url": d.get("webpage_url", ""),
        "license": d.get("license", ""),
        "author": d.get("uploader") or d.get("channel") or "",
    }


def write_source(sdir, meta):
    (sdir / "source.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))


def cleanup(sdir, keep):
    for f in sdir.iterdir():
        if f.is_file() and f.name not in keep:
            try:
                f.unlink()
            except OSError:
                pass


def strip_html(s) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def clean_stderr(stderr) -> str:
    """Return the last meaningful error line from yt-dlp/ffmpeg stderr."""
    noise = ("frame=", "fps=", "size=", "speed=", "Press [q]", "Stream #",
             "Output #", "Metadata:", "handler_name", "vendor_id",
             "creation_time", "track 1", "major_brand", "minor_version",
             "compatible_brands", "Duration:", "Stream mapping")
    for line in reversed((stderr or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(n) for n in noise):
            continue
        return line[-500:]
    return "unknown error"
