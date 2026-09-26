import re
from pathlib import Path

from . import remotion_render
from .utils import ffmpeg, run

LEAD_S = 0.4          # silence before narration in each scene
TAIL_S = 0.4          # silence after narration in each scene
MUSIC_VOLUME = 0.18   # background music level relative to narration


def run_assembly(ctx):
    """Render the finished video with Remotion (fallback: ffmpeg)."""
    log = ctx["logger"]
    progress = ctx.get("progress", lambda p: None)
    scenes = ctx["scenes"]
    settings = ctx["settings"]
    out_dir = ctx["dir"] / "stage5_assembly"
    out_dir.mkdir(parents=True, exist_ok=True)

    W, H = parse_resolution(settings.get("resolution", "1920x1080"))
    fps = int(settings.get("fps", 30))

    documentary = (ctx.get("visual_style") or settings.get("visual_style") or "stock") == "documentary"
    if documentary:
        log("Documentary style detected — applying sepia / film grain / letterbox grade")

    durations = [scene_duration(scene) for scene in scenes]
    total = round(sum(durations), 2)
    renderer = (settings.get("renderer") or "remotion").lower()

    if renderer == "remotion":
        if not remotion_render.is_available():
            log("Remotion not installed (node_modules missing) — using ffmpeg assembly")
        else:
            log("Using Remotion renderer (motion graphics + transitions)")
            try:
                remotion_render.render(ctx, scenes, durations, out_dir, W, H, fps,
                                       documentary, log, progress)
                progress(100)
                log(f"Final video ready: {total:.1f}s")
                return {
                    "final": f"/media/{ctx['pid']}/stage5_assembly/final.mp4",
                    "duration": total,
                    "scenes": len(scenes),
                    "resolution": f"{W}x{H}",
                    "renderer": "remotion",
                }
            except Exception as e:  # noqa: BLE001 - fall back to ffmpeg
                log(f"Remotion render failed — falling back to ffmpeg assembly: {e}")

    segs = []
    for i, (scene, dur) in enumerate(zip(scenes, durations)):
        seg = out_dir / f"seg_{i + 1:02d}.mp4"
        log(f"[scene {scene['index']}] rendering segment ({dur}s)…")
        build_segment(ctx, scene, seg, dur, W, H, fps, log, documentary=documentary)
        segs.append(seg)
        progress(5 + int(55 * (i + 1) / max(len(scenes), 1)))

    concat = out_dir / "video_concat.mp4"
    log("Concatenating scene segments…")
    concat_segments(segs, concat, log)
    progress(75)

    final = out_dir / "final.mp4"
    music = ctx.get("music_media") or {}
    if music.get("rel") and (ctx["dir"] / music["rel"]).exists():
        log("Mixing background music…")
        mix_music(concat, ctx["dir"] / music["rel"], total, final, log)
    else:
        log("No background music — finalizing without it")
        run([ffmpeg(), "-y", "-i", str(concat), "-c", "copy",
             "-movflags", "+faststart", str(final)], log=log)

    progress(100)
    log(f"Final video ready: {total:.1f}s")
    return {
        "final": f"/media/{ctx['pid']}/stage5_assembly/final.mp4",
        "duration": total,
        "scenes": len(scenes),
        "resolution": f"{W}x{H}",
        "renderer": "ffmpeg",
    }


def build_segment(ctx, scene, seg, dur, W, H, fps, log, documentary=False):
    proj = ctx["dir"]
    vm = scene.get("visual_media") or {}
    inputs = []
    fc = []

    # ---- video ----
    vtype = vm.get("type")
    if vtype == "video" and vm.get("clip") and (proj / vm["clip"]).exists():
        inputs += ["-stream_loop", "-1", "-i", str(proj / vm["clip"])]
        base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setpts=PTS-STARTPTS,fps={fps}")
    elif vtype == "image" and vm.get("image") and (proj / vm["image"]).exists():
        frames = max(int(round(dur * fps)), 1)
        inputs += ["-i", str(proj / vm["image"])]
        base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},"
                f"zoompan=z='min(1.0+0.0004*on,1.15)':d={frames}"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps}")
    else:
        inputs += ["-f", "lavfi", "-i", f"color=c=0x151a2a:s={W}x{H}:r={fps}"]
        base = "[0:v]null"

    if documentary:
        base += "," + documentary_grade(H)

    # ---- captions (motion graphics) ----
    settings = ctx.get("settings", {})
    caption = caption_text(scene) if settings.get("captions", True) else None
    font = find_font()
    if caption and font:
        cap_file = seg.parent / f"{seg.stem}_caption.txt"
        cap_file.write_text(caption, encoding="utf-8")
        fc.append(f"{base},{drawtext_filter(font, cap_file, dur)}[v]")
    else:
        fc.append(f"{base}[v]")

    # ---- audio ----
    audio_labels = []
    idx = 1
    if scene.get("audio") and (proj / scene["audio"]).exists():
        inputs += ["-i", str(proj / scene["audio"])]
        fc.append(f"[{idx}:a]adelay={int(LEAD_S * 1000)}|{int(LEAD_S * 1000)}[n{idx}]")
        audio_labels.append(f"[n{idx}]")
        idx += 1
    if scene.get("sfx_media") and scene["sfx_media"].get("file") and (proj / scene["sfx_media"]["file"]).exists():
        inputs += ["-i", str(proj / scene["sfx_media"]["file"])]
        fc.append(f"[{idx}:a]adelay=0|0[s{idx}]")
        audio_labels.append(f"[s{idx}]")
        idx += 1

    if audio_labels:
        if len(audio_labels) == 1:
            fc.append(f"{audio_labels[0]}apad[a]")
        else:
            fc.append(f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:normalize=0,apad[a]")
    else:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        fc.append(f"[{idx}:a]anull[a]")

    cmd = [ffmpeg(), "-y", *inputs, "-filter_complex", ";".join(fc),
           "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-r", str(fps),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-ac", "2", str(seg)]
    run(cmd, log=log)


def concat_segments(segs, out, log):
    lst = out.parent / "concat.txt"
    with open(lst, "w") as f:
        for s in segs:
            f.write(f"file '{s}'\n")
    run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(out)], log=log)


def mix_music(video, music_path, total, out, log):
    run([ffmpeg(), "-y",
         "-i", str(video),
         "-stream_loop", "-1", "-i", str(music_path),
         "-filter_complex",
         f"[1:a]volume={MUSIC_VOLUME}[m];"
         "[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
         "-map", "0:v", "-map", "[a]",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)], log=log)


def scene_duration(scene) -> float:
    if scene.get("audio_duration"):
        d = float(scene["audio_duration"]) + LEAD_S + TAIL_S
    elif scene.get("duration"):
        d = float(scene["duration"])
    else:
        words = len((scene.get("narration") or "").split())
        d = words * 0.42 + LEAD_S + TAIL_S
    return round(max(d, 1.2), 2)


def parse_resolution(s):
    w, h = s.lower().replace("x", " ").split()
    return int(w), int(h)


def documentary_grade(H):
    """ffmpeg filter chain for the archival 1990s BBC documentary look.

    Faded/warm sepia tone, vignette, film grain, and cinematic letterbox bars.
    """
    bar = int(round(H * 0.11))
    return (
        "eq=saturation=0.45:contrast=1.05:brightness=0.005,"
        "colorbalance=rs=.08:gs=.03:bs=-.10:rm=.10:gm=.04:bm=-.13:rh=.08:gh=.01:bh=-.15,"
        "vignette=angle=PI/5,"
        "noise=alls=16:allf=t+u,"
        f"drawbox=x=0:y=0:w=iw:h={bar}:color=black:t=fill,"
        f"drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black:t=fill"
    )


def find_font():
    for p in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if Path(p).exists():
            return p
    return None


def caption_text(scene):
    n = (scene.get("narration") or "").strip()
    if not n:
        n = (scene.get("visual_media") or {}).get("source_title") or ""
    if not n:
        return None
    m = re.match(r"([^.!?]+[.!?])", n)
    s = (m.group(1) if m else n).strip()
    if len(s) > 90:
        s = s[:87].rstrip() + "…"
    return s or None


def drawtext_filter(font, cap_file, dur):
    fade_in = 0.6
    fade_out = 0.8
    alpha = (f"if(lt(t,{fade_in}),t/{fade_in},"
             f"if(gt(t,{dur - fade_out:.2f}),({dur - fade_out:.2f}-t)/{fade_out}+1,1))")
    return (f"drawtext=fontfile='{font}':textfile='{cap_file}':"
            f"fontcolor=white:fontsize=44:"
            f"box=1:boxcolor=black@0.45:boxborderw=18:"
            f"x=(w-text_w)/2:y=h-150:alpha='{alpha}'")
