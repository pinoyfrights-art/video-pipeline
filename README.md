# Video Pipeline

A staged video-generation pipeline: paste a script, and it produces a finished video with
voiceover, visuals, sound effects, motion graphics, and background music — with each stage
individually runnable and testable from a simple web page.

## Stages

1. **Script** — paste a script; it is split into scenes (blank line = new scene).
2. **Voiceover** — natural narration per scene via `edge-tts` (free, no API key).
3. **Visuals** — YouTube **Creative Commons** clips (720p, license-verified via `yt-dlp`),
   with a **Wikimedia Commons** CC/public-domain image fallback. AI-image/video hooks are left open.
4. **Audio** — background music + sound effects from **Wikimedia Commons** (CC/PD audio),
   with a procedural fallback (ambient pad / whoosh) when no match is found.
5. **Assembly** — `ffmpeg`: Ken Burns motion on images, animated lower-third captions,
   scene timing, and a final mix of narration + music (ducked) + SFX into a 1080p H.264 MP4.

## Run

```bash
./run.sh
```

Then open http://127.0.0.1:8000

Requirements: Python 3.10+, `ffmpeg`/`ffprobe` on PATH, Node.js (used by `yt-dlp` for YouTube).

## Script format

Blank lines separate scenes. Optional per-scene directives:

```
visual: golden retriever puppy running in a park
sfx: playful dog bark
music: upbeat acoustic
Golden retrievers are one of the friendliest dog breeds in the world.
```

- `visual:` — search keywords for the scene's image/video (defaults to the first sentence).
- `sfx:` — sound effect keywords.
- `music:` — background music mood/keywords.
- `voice:` — override TTS voice for this scene.
- `duration:` — optional target scene length in seconds (e.g. `duration: 5s`).

## Notes

- **Licensing** — every downloaded visual/audio records its source, author, and license in a
  `source.json` next to the asset and in the UI caption. Keep the CC attribution if you publish.
- **Wikimedia robot policy** — Wikimedia Commons rejects requests from placeholder user agents
  (e.g. `test@example.com`). The default user agent in `app/pipeline/stage3_visuals.py` and
  `app/pipeline/stage4_audio.py` is a working placeholder; please replace its contact with your
  own before any real use. Requests are throttled and retried on 429/403.
- **Where outputs live** — everything is under `data/<project-id>/`, grouped by stage:
  `stage2_voiceover/`, `stage3_visuals/`, `stage4_audio/`, `stage5_assembly/` (final video is
  `stage5_assembly/final.mp4`).
