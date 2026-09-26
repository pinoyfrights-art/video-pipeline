import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .utils import ffmpeg, probe_duration, run

UA = "VideoPipeline/1.0 (+https://example.net/video-pipeline; contact: pipeline@example.net)"
AUDIO_EXTS = (".ogg", ".oga", ".opus", ".flac", ".mp3", ".wav", ".m4a", ".webm", ".aac")

MUSIC_FALLBACKS = ["ambient music", "instrumental music", "classical music"]

_last_request = 0.0
MIN_INTERVAL = 1.5
MAX_AUDIO_BYTES = 40 * 1024 * 1024


def _throttle():
    global _last_request
    wait = _last_request + MIN_INTERVAL - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_request = time.time()


def _open(url, timeout, log):
    """Open a URL with polite throttling, retrying on rate-limit and timeout."""
    last_exc = None
    for attempt in range(3):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_exc = e
            time.sleep(2 * (attempt + 1))
            continue
    raise last_exc


def run_audio(ctx):
    """Produce a background-music track and per-scene sound effects."""
    log = ctx["logger"]
    progress = ctx.get("progress", lambda p: None)
    scenes = ctx["scenes"]
    out_dir = ctx["dir"] / "stage4_audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    progress(5)
    music = acquire_music(ctx, scenes, out_dir, log)
    progress(50)

    sfx_results = []
    sfx_scenes = [s for s in scenes if s.get("sfx")]
    for i, scene in enumerate(sfx_scenes):
        progress(50 + int(45 * i / max(len(sfx_scenes), 1)))
        item = acquire_sfx(ctx, scene, out_dir, log)
        scene["sfx_media"] = {
            k: v for k, v in item.items()
            if k in ("file", "duration", "source", "source_title", "source_url",
                     "license", "author", "procedural", "query")
        }
        if item.get("file", "").startswith("/media/"):
            scene["sfx_media"]["file"] = item["file"].split("/", 3)[-1]
        sfx_results.append(item)
    progress(95)
    log(f"Audio complete: music {'ready' if music else 'missing'}, {len(sfx_results)} SFX")
    return {"music": music, "sfx": sfx_results}


def acquire_music(ctx, scenes, out_dir, log):
    pid = ctx["pid"]
    queries = [s.get("music") for s in scenes if s.get("music")]
    queries += MUSIC_FALLBACKS
    for q in queries:
        log(f"  searching music: '{q}'")
        try:
            item = search_wikimedia_audio(q, log)
            if not item:
                continue
            dst = out_dir / "music.mp3"
            log(f"  downloading music: {item['source_title']}")
            dur = download_audio(item, dst, log)
            write_meta(out_dir, "music.json", item)
            return {
                "type": "music",
                "file": f"/media/{pid}/stage4_audio/music.mp3",
                "rel": "stage4_audio/music.mp3",
                "duration": round(dur, 2),
                "procedural": False,
                **item,
            }
        except Exception as e:  # noqa: BLE001 - fall through to next query
            log(f"  music source failed: {e}")
            continue

    log("  no music found — generating procedural ambient pad")
    dst = out_dir / "music.mp3"
    procedural_music(dst, log=log)
    return {
        "type": "music",
        "file": f"/media/{pid}/stage4_audio/music.mp3",
        "rel": "stage4_audio/music.mp3",
        "duration": round(probe_duration(dst), 2),
        "procedural": True,
        "source": "Procedural",
        "source_title": "Generated ambient pad",
        "license": "",
        "author": "",
        "source_url": "",
    }


def acquire_sfx(ctx, scene, out_dir, log):
    pid = ctx["pid"]
    text = (scene.get("sfx") or "").strip()
    for q in sfx_queries(text):
        log(f"  [scene {scene['index']}] searching SFX: '{q}'")
        try:
            item = search_wikimedia_audio(q, log)
            if not item:
                continue
            dst = out_dir / f"{scene['id']}_sfx.mp3"
            log(f"  [scene {scene['index']}] downloading SFX: {item['source_title']}")
            dur = download_audio(item, dst, log)
            write_meta(out_dir, f"{scene['id']}_sfx.json", item)
            return {
                "type": "sfx", "scene": scene["id"], "index": scene["index"],
                "file": f"/media/{pid}/stage4_audio/{scene['id']}_sfx.mp3",
                "duration": round(dur, 2), "procedural": False, "query": text,
                **item,
            }
        except Exception as e:  # noqa: BLE001
            log(f"  SFX source failed: {e}")
            continue

    log(f"  [scene {scene['index']}] no SFX found — generating whoosh")
    dst = out_dir / f"{scene['id']}_sfx.mp3"
    procedural_sfx(dst, log=log)
    return {
        "type": "sfx", "scene": scene["id"], "index": scene["index"],
        "file": f"/media/{pid}/stage4_audio/{scene['id']}_sfx.mp3",
        "duration": round(probe_duration(dst), 2), "procedural": True,
        "query": text, "source": "Procedural", "source_title": "Generated whoosh",
        "license": "", "author": "", "source_url": "",
    }


def sfx_queries(text):
    words = text.split()
    out = []
    for q in (text, " ".join(words[-2:]), words[-1] if words else ""):
        q = q.strip()
        if q and q not in out:
            out.append(q)
    return out[:3]


# ---------------------------------------------------------------- wikimedia
def search_wikimedia_audio(query, log):
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": 10,
        "prop": "imageinfo", "iiprop": "url|extmetadata|mediatype|size", "format": "json",
    }
    url = api + "?" + urllib.parse.urlencode(params)
    try:
        with _open(url, 30, log) as r:
            data = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        log(f"    Wikimedia search failed: {e}")
        return None
    pages = (data.get("query") or {}).get("pages") or {}
    candidates = []
    for _, page in pages.items():
        ii = (page.get("imageinfo") or [None])[0]
        if not ii or ii.get("mediatype") != "AUDIO":
            continue
        u = ii.get("url") or ""
        ext = Path(urllib.parse.urlparse(u).path).suffix.lower()
        if ext not in AUDIO_EXTS:
            continue
        size = ii.get("size") or 0
        if size and size > MAX_AUDIO_BYTES:
            continue
        em = ii.get("extmetadata") or {}
        candidates.append({
            "url": u,
            "ext": ext,
            "size": size,
            "source": "Wikimedia Commons",
            "source_title": (page.get("title") or "").replace("File:", "", 1),
            "source_url": ii.get("descriptionurl", ""),
            "license": strip_html(em.get("LicenseShortName", {}).get("value", "")),
            "author": strip_html(em.get("Artist", {}).get("value", "")),
        })
    if not candidates:
        return None
    # prefer compressed formats, then smaller files
    candidates.sort(key=lambda c: (0 if c["ext"] in (".mp3", ".m4a", ".aac", ".opus", ".ogg", ".oga") else 1, c["size"]))
    return candidates[0]


def download_audio(item, dst, log):
    with _open(item["url"], 120, log) as r:
        raw = r.read()
    src = dst.parent / f"{dst.stem}_src{item['ext']}"
    src.write_bytes(raw)
    run([ffmpeg(), "-y", "-i", str(src), "-vn", "-ar", "44100", "-ac", "2",
         "-c:a", "libmp3lame", "-b:a", "192k", str(dst)], log=log)
    try:
        src.unlink()
    except OSError:
        pass
    return probe_duration(dst)


def write_meta(out_dir, name, item):
    meta = {k: v for k, v in item.items() if k != "url" and k != "ext"}
    (out_dir / name).write_text(json.dumps(meta, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------- procedural
def procedural_music(dst, dur=30.0, log=None):
    run([ffmpeg(), "-y",
         "-f", "lavfi", "-i", f"sine=frequency=220:duration={dur}",
         "-f", "lavfi", "-i", f"sine=frequency=277.18:duration={dur}",
         "-f", "lavfi", "-i", f"sine=frequency=329.63:duration={dur}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
         "-filter_complex",
         "[0:a]volume=0.15[a];[1:a]volume=0.12[b];"
         "[2:a]volume=0.10[c];[3:a]volume=0.07[d];"
         f"[a][b][c][d]amix=inputs=4:duration=longest,aecho=0.8:0.5:80:0.25,"
         f"afade=t=in:d=2,afade=t=out:st={dur-3}:d=3[out]",
         "-map", "[out]", "-ar", "44100", "-ac", "2",
         "-c:a", "libmp3lame", "-b:a", "192k", str(dst)], log=log)


def procedural_sfx(dst, log=None):
    run([ffmpeg(), "-y",
         "-f", "lavfi", "-i", "anoisesrc=color=pink:duration=2.0:amplitude=0.6",
         "-af", "afade=t=in:d=0.4,afade=t=out:st=1.1:d=0.9,lowpass=f=1500,volume=0.7",
         "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(dst)], log=log)


def strip_html(s) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()
