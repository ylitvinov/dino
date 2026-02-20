# Grok Video Pipeline

Video generation via xAI Grok Imagine API. Chain-generates clips using last-frame-as-input technique for continuity, then concatenates with crossfade.

## Rules

- **NEVER run the pipeline** (`python generate.py ...`) — the user runs it manually. Only edit code and review output.

## Commands

```bash
# Run from grok-video/ directory
python generate.py --config config.json --api-key YOUR_KEY --output final.mp4 --output-dir clips

# Or via env var
export XAI_API_KEY=...
python generate.py --config config.json
```

Requires: `requests`, `ffmpeg`/`ffprobe` on PATH.

## Architecture

Single-file pipeline (`generate.py`):

1. Reads `config.json` with initial image, clip prompts, duration, resolution, crossfade
2. For each clip: submit to Grok API → poll until ready → download → extract last frame
3. Last frame of clip N becomes input image for clip N+1 (continuity chain)
4. Concatenate all clips with ffmpeg xfade filter

### API (xAI Grok Imagine)

- Base: `https://api.x.ai/v1`
- Model: `grok-imagine-video`
- Auth: Bearer token (`XAI_API_KEY`)
- Submit: `POST /videos/generations` (prompt + optional base64 image_url)
- Poll: `GET /videos/{request_id}` → `video.url` when ready
- Duration: 6s per clip, resolution: 720p

### Config format

```json
{
  "initial_image": "start.png",
  "resolution": "720p",
  "duration": 6,
  "crossfade": 0.5,
  "clips": [
    {"prompt": "Scene description", "duration": 6}
  ]
}
```

### Output structure

```
clips/          # intermediate clips + last-frame images
  clip_000.mp4
  frame_000.jpg
final.mp4       # concatenated result
```
