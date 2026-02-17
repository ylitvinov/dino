# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated video generation pipeline for a children's animated short ("Topa and Pusha: The Best Day") using KIE.ai's Kling 3.0 API. The pipeline generates reference images for characters/backgrounds (Elements), then generates 23 video shots across 8 scenes, with resume support. Elements are shared across scenarios in `output/elements/`; shots are scoped per scenario in `output/<scenario_name>/`.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Full pipeline (elements -> shots -> download)
python -m pipeline.runner run-all -s scenario/scenario.yaml

# Individual steps
python -m pipeline.runner generate-elements -s scenario/scenario.yaml
python -m pipeline.runner generate-scene -s scenario/scenario.yaml 1   # scene by id
python -m pipeline.runner download -s scenario/scenario.yaml
python -m pipeline.runner status -s scenario/scenario.yaml

# Verbose/debug mode
python -m pipeline.runner -v generate-scene -s scenario/scenario.yaml 1

# Custom config
python -m pipeline.runner -c my-config.yaml run-all -s scenario/scenario.yaml
```

No test suite exists yet.

## Architecture

**Three-phase pipeline**: generate element reference images -> generate video shots -> download outputs.

All generation is async (KIE.ai returns task IDs, pipeline polls for completion). State is persisted after every task, enabling resume on interruption.

### Output structure

```
output/
  elements/              # shared across all scenarios
    Topa/Topa1.png       # element images in named subdirectories
    Pusha/Pusha1.png
    Valley/Valley1.png
    ...
  elements_status.json   # shared element CDN URLs
  <scenario_name>/       # per-scenario (derived from input filename stem)
    shots/
    status.json          # per-scenario shot status
```

### Data flow

1. `scenario.yaml` defines elements (characters + backgrounds) with reference prompts, and 8 scenes with shot-level prompts using `@ElementName` syntax
2. `generate_elements` creates reference images via KIE image API, stores **CDN URLs** in `output/elements_status.json` (shared)
3. `generate_shots` reads those CDN URLs from shared status, passes them as `kling_elements` array in video generation requests; writes shots to `output/<scenario_name>/`
4. Element CDN URLs are the critical link between phases — they must be preserved in `elements_status.json`

### Key modules

- **`client.py`** — async KIE.ai HTTP client (`KieClient`). Handles both nested and flat API response formats. Retry with exponential backoff on 429/5xx. Context manager pattern.
- **`generate_elements.py`** — generates element reference images. Skips elements whose folder already has images. Saves as `{Name}{N}.png` in `output/elements/{Name}/`.
- **`generate_shots.py`** — generates video shots per scene. CLI command `generate-scene` takes scene id as argument. Tracks progress in `status.json`.
- **`scenario_parser.py`** — maps `scenario.yaml` to dataclasses in `models.py`. Note: `generate_elements.py` also loads raw YAML separately to access `reference_prompts` that aren't in the parsed model.
- **`runner.py`** — Click CLI. Each command imports its dependencies lazily to keep `--help` fast.

### API details (KIE.ai)

- Base URL: `https://api.kie.ai`
- Auth: Bearer token (plain API key, no JWT)
- Create task: `POST /api/v1/jobs/createTask` with model `kling-3.0/video` or `kling-3.0/image`
- Poll task: `GET /api/v1/jobs/{task_id}`
- Elements are passed inline per-request via `kling_elements` array (not persistent server-side)
- Task statuses: `pending` -> `processing` -> `completed` | `failed`

## Content

The scenario is a 2-minute non-verbal 3D Pixar-style cartoon for toddlers (3-4 years). Two versions of the script exist:
- `scenario/topa_push_scenario.md` — full production script with detailed camera/lighting/audio per shot
- `scenario/topa_push_scenario_short.md` — condensed version used as source for `scenario.yaml`

Language in scenario files and comments is mixed English/Russian.

## Reference Docs

- [Kling 3.0 Video Generation Guide](docs/kling3-guide.md) — prompt structure, tips, negative prompts, multi-shot, audio, known limitations
