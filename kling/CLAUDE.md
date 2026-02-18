# Kling Video Pipeline

Automated video generation pipeline for a children's animated short ("Topa and Pusha: The Best Day") using KIE.ai's Kling 3.0 API. Generates reference images for characters/backgrounds (Elements), then generates 23 video shots across 8 scenes, with resume support.

## Commands

All commands run from `kling/` directory.

```bash
pip install -r requirements.txt

# Full pipeline (elements -> shots -> download)
python -m pipeline.runner run-all -s scenario/scenario.yaml

# Individual steps
python -m pipeline.runner upload-elements -s scenario/scenario.yaml
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

**Three-phase pipeline**: upload element images -> generate video shots -> download outputs.

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
    scene_status.json    # per-scenario shot status
```

### Data flow

1. `scenario.yaml` defines elements (characters + backgrounds) with reference prompts, and 8 scenes with shot-level prompts using `@ElementName` syntax
2. `upload_elements` uploads local images from `output/elements/{Name}/` to KIE.ai file storage, saves returned **file URLs** in `output/elements_status.json` (shared). URLs expire after 3 days.
3. `generate_shots` reads those URLs from shared status, passes them as `kling_elements` array in video generation requests; writes shots to `output/<scenario_name>/`
4. Element file URLs are the critical link between phases — they must be preserved in `elements_status.json`. Re-upload if expired.

### Key modules

- **`client.py`** — async KIE.ai HTTP client (`KieClient`). Handles both nested and flat API response formats. Retry with exponential backoff on 429/5xx. Context manager pattern. Includes `upload_file()` for KIE file storage.
- **`upload_elements.py`** — uploads local element images to KIE.ai file storage. Skips elements that already have URLs in status. Saves file URLs to `elements_status.json`.
- **`generate_shots.py`** — generates video shots per scene. CLI command `generate-scene` takes scene id as argument. Tracks progress in `scene_status.json`.
- **`scenario_parser.py`** — maps `scenario.yaml` to dataclasses in `models.py`.
- **`runner.py`** — Click CLI. Each command imports its dependencies lazily to keep `--help` fast.

### API details (KIE.ai)

- Base URL: `https://api.kie.ai`
- Auth: Bearer token (plain API key, no JWT)
- Create task: `POST /api/v1/jobs/createTask` with model `kling-3.0/video` or `kling-3.0/image`
- Poll task: `GET /api/v1/jobs/{task_id}`
- File upload: `POST https://kieai.redpandaai.co/api/file-stream-upload` (multipart/form-data). Files expire after 3 days.
- Elements are passed inline per-request via `kling_elements` array (not persistent server-side)
- Task statuses: `pending` -> `processing` -> `completed` | `failed`

## Content

The scenario is a 2-minute non-verbal 3D Pixar-style cartoon for toddlers (3-4 years). Two versions of the script exist:
- `scenario/topa_push_scenario.md` — full production script with detailed camera/lighting/audio per shot
- `scenario/topa_push_scenario_short.md` — condensed version used as source for `scenario.yaml`

Language in scenario files and comments is mixed English/Russian.

## Reference Docs

- [Kling 3.0 Video Generation Guide](docs/kling3-guide.md) — prompt structure, tips, negative prompts, multi-shot, audio, known limitations
- [KIE.ai Kling 3.0 API Reference](docs/kie-kling3-api.md) — endpoints, elements, file upload API, request/response formats
