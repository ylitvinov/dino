# typescript

Pipeline for generating short-form video content from text quotes.

## Quick start
```bash
cd /Users/yurylitvinov/Projects-dino/typescript
python -m src produce en
```

## Commands
- `python -m src tts <lang> [quote_ids...] [-f]` — generate TTS (`-f` to regenerate)
- `python -m src video <lang> [quote_ids...] [-f]` — build videos (`-f` to rebuild)
- `python -m src produce <lang> [quote_ids...] [-f]` — full pipeline (`-f` to regenerate)
- `python -m src clips_annotate [-f]` — auto-annotate clip text zones via Claude Vision
- `python -m src clips_preview [--open]` — generate preview PNGs with zone overlays

## Structure
```
en/                     # language directory
  atticus_1.txt         # quote text (one line per quote line)
  marcus_1.txt
  status.json           # pipeline & deploy status
  output/               # generated voiceovers & videos
clips/                  # pre-generated .mp4 clips
```

## Config
All API keys and settings in `config.yaml`.
