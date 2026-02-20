# typescript

Pipeline for generating short-form video content from text quotes.

## Quick start
```bash
cd /Users/yurylitvinov/Projects-dino/typescript
python -m pipeline status
python -m pipeline generate-clips
python -m pipeline produce
```

## Commands
- `python -m pipeline generate-clips` — generate clip library from images/
- `python -m pipeline translate [quote_ids...]` — translate quotes
- `python -m pipeline voiceover [quote_ids...]` — generate TTS
- `python -m pipeline assemble [quote_ids...]` — assemble videos
- `python -m pipeline produce [quote_ids...]` — full pipeline
- `python -m pipeline deploy-status [quote_ids...]` — show deploy status
- `python -m pipeline status` — show pipeline status

## Config
All API keys and settings in `config.yaml`.
