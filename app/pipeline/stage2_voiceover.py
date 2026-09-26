import asyncio

import edge_tts

from .utils import concat_audio, probe_duration


async def _synth(text, voice, rate, pitch, out):
    com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await com.save(str(out))


def run_voiceover(ctx):
    """Generate per-scene narration with edge-tts and a combined track.

    ctx keys: pid, root, dir, scenes, settings, logger.
    """
    log = ctx["logger"]
    scenes = ctx["scenes"]
    settings = ctx["settings"]
    out_dir = ctx["dir"] / "stage2_voiceover"
    out_dir.mkdir(parents=True, exist_ok=True)

    voice = settings.get("voice", "en-US-AriaNeural")
    rate = settings.get("voice_rate", "+0%")
    pitch = settings.get("voice_pitch", "+0Hz")

    results = []
    for scene in scenes:
        if not scene.get("narration"):
            log(f"[scene {scene['index']}] no narration — skipped")
            continue
        out = out_dir / f"{scene['id']}.mp3"
        use_voice = scene.get("voice") or voice
        log(f"[scene {scene['index']}] voiceover ({len(scene['narration'])} chars, voice={use_voice})")
        asyncio.run(_synth(scene["narration"], use_voice, rate, pitch, out))

        dur = round(probe_duration(out), 2)
        scene["audio"] = f"stage2_voiceover/{scene['id']}.mp3"
        scene["audio_duration"] = dur
        results.append({
            "scene": scene["id"],
            "index": scene["index"],
            "file": f"/media/{ctx['pid']}/stage2_voiceover/{scene['id']}.mp3",
            "duration": dur,
        })

    combined = None
    total = 0.0
    paths = [out_dir / f"{sc['id']}.mp3" for sc in scenes if sc.get("narration")]
    if paths:
        log("Combining narration track…")
        combined_path = out_dir / "narration_full.mp3"
        concat_audio(paths, combined_path, gap=0.4, log=log)
        total = round(probe_duration(combined_path), 2)
        combined = f"/media/{ctx['pid']}/stage2_voiceover/narration_full.mp3"
        log(f"Combined narration ready: {total}s")

    return {
        "scenes": results,
        "combined": combined,
        "total_duration": total,
        "voice": voice,
    }
