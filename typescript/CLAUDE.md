# typescript

Pipeline for generating short-form video content from text quotes.

## Quick start
```bash
cd /Users/yurylitvinov/Projects-dino/typescript
python -m src status
python -m src produce en
```

## Commands
- `python -m src voiceover <lang> [quote_ids...]` — generate TTS
- `python -m src assemble <lang> [quote_ids...]` — assemble videos
- `python -m src produce <lang> [quote_ids...]` — full pipeline (voiceover + assemble)
- `python -m src deploy_status <lang> [quote_ids...]` — show deploy status
- `python -m src status [lang...]` — show pipeline status

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
