# Kling 3.0 — Video Generation Guide

## Key Features

### Resolution & Duration
- **Native 4K** (3840x2160) at **60 fps**
- **3–15 seconds** per generation, flexible duration
- Two modes: `std` (standard) and `pro` (higher resolution)

### Multi-Shot Generation
- Up to **6 distinct shots** in a single generation
- Per-shot control: `prompt` + `duration` (1–12 sec each)
- Model understands cinematic language: profile shot, macro close-up, tracking shot, POV, shot-reverse-shot

### Element References
- Reference characters/backgrounds via `@ElementName` syntax in prompts
- Elements = 2–4 reference images (JPG/PNG, min 300x300px, max 10MB each)
- Elements are passed per-request via `kling_elements` array (not stored server-side)
- File URLs expire after 3 days — re-upload if expired

### Native Audio
- Character speech in 5 languages (EN, CN, JP, KR, ES)
- Up to 3-person dialogue with lip-sync
- Sound effects enabled by default in multi-shot mode

### Start/End Frame Control
- Specify start and/or end frame images for smooth interpolation
- Multi-shot mode supports first frame only

---

## Scenario YAML Format

Our pipeline uses `scenario.yaml` to define elements and scenes. The pipeline reads this file, uploads element images, and sends multi-shot requests to KIE.ai.

### Top-level structure

```yaml
style_prefix: "3D cartoon for toddlers, Pixar-style, soft rounded shapes..."

kling_elements:
  - name: "Topa"
    description: "Bright-green baby triceratops, big brown eyes, orange frill."
  - name: "Pusha"
    description: "Fluffy purple baby pterodactyl, big blue eyes, pink beak."
  - name: "Valley"
    description: "Prehistoric valley, colorful flowers, friendly volcanoes, river."

scenes:
  - id: 1
    background: "Valley"
    lighting: "Sunrise golden hour"
    kling_elements: ["Valley", "Topa"]
    multi_prompt:
      - prompt: "EWS, slow dolly push. @Valley at sunrise — morning mist..."
        duration: 5
      - prompt: "MS on @Topa sleeping curled on a big leaf..."
        duration: 5
```

### Fields

| Field | Level | Description |
|-------|-------|-------------|
| `style_prefix` | top | Prepended to every shot prompt. Defines visual style. |
| `kling_elements` | top | Character/background definitions with `name` and `description`. Reference images live in `output/elements/{Name}/`. |
| `scenes[].id` | scene | Scene number (used in CLI: `generate-scene -s scenario.yaml 1`). |
| `scenes[].background` | scene | Background element name. |
| `scenes[].lighting` | scene | Lighting description for the scene. |
| `scenes[].kling_elements` | scene | Which elements this scene references (names from top-level list). Only these elements are sent to the API for this scene. |
| `scenes[].multi_prompt` | scene | Array of shots. Each shot = `prompt` + `duration`. |
| `multi_prompt[].prompt` | shot | Shot prompt text. Use `@Name` to reference elements. Max 500 chars. |
| `multi_prompt[].duration` | shot | Shot duration in seconds (1–12). |

### How it maps to the API

The pipeline converts each scene into a single multi-shot API request:

```
scene.multi_prompt        -> input.multi_prompt (array of {prompt, duration})
scene.kling_elements      -> input.kling_elements (with uploaded file URLs)
style_prefix + shot.prompt -> each multi_prompt[].prompt
```

Multi-shot mode is always enabled (`multi_shots: true`). Sound is on by default.

---

## Shot Prompt Structure

Each shot prompt follows this pattern:

```
[Camera] [Action/Subject with @Element refs] [Technical details]
```

### Camera abbreviations

Use standard abbreviations at the start of each prompt:

| Abbreviation | Meaning |
|-------------|---------|
| `EWS` | Extreme wide shot |
| `WS` | Wide shot |
| `MS` | Medium shot |
| `CU` | Close-up |
| `ECU` | Extreme close-up |

### Element references

Use `@ElementName` inline wherever the element appears in the action:

```yaml
- prompt: "MS on @Topa sleeping curled on a big leaf. Warm sunbeam reaches his face."
```

The `@Name` must match a name from the scene's `kling_elements` list.

### Example shot prompts

**Establishing shot (no character):**
```yaml
- prompt: "EWS, slow dolly push. @Valley at sunrise — morning mist drifting low, volumetric light rays through ferns, pink-orange sky. Winding river reflects warm colors. Deep focus, cinematic composition."
  duration: 5
```

**Character action:**
```yaml
- prompt: "MS on @Topa sleeping curled on a big leaf. Warm sunbeam reaches his face. He scrunches nose, yawns wide showing tiny tongue, opens big brown eyes, stretches chubby legs one by one. Shallow DOF, bokeh background, golden rim light."
  duration: 5
```

**Close-up with emotion:**
```yaml
- prompt: "CU low angle. @Topa stands, shakes vigorously — orange frill wiggles comically. Looks at camera with excited eyes, beams with joy, spreads front paws wide. Golden rim light outlines bright-green body. Soft-focused @Valley behind."
  duration: 5
```

---

## Tips & Best Practices

### 1. Describe Each Shot as a Director
Start with camera type/movement, then subject and action, then atmosphere/technical. Keep each prompt focused on one clear moment.

### 2. Be Precise About Motion
- Describe both **subject actions** and **camera behavior**
- Cinematic terms: `dolly push`, `whip-pan`, `crash zoom`, `tracking shot`, `slow dolly push`
- Camera movement should be **motivated**: follow a character, reveal information, emphasize emotion

### 3. Anchor Characters via Elements
Don't re-describe characters in every prompt. The `@ElementName` reference + uploaded images handle identity. Focus the prompt on **what the character does**, not what they look like. You can mention distinctive features (e.g. "orange frill wiggles") for emphasis.

### 4. Use Temporal Sequencing Within Shots
For 5-second shots, describe 2–3 beats of action in order:
```
He scrunches nose, yawns wide showing tiny tongue, opens big brown eyes, stretches chubby legs one by one.
```

### 5. Include Lighting and Depth Cues
Technical details at the end of the prompt improve quality:
- `Shallow DOF, bokeh background`
- `Golden rim light`
- `Deep focus, cinematic composition`
- `Volumetric light rays`

### 6. Use Negative Prompts When Needed
For controlling unwanted artifacts (configured at API level, not in scenario YAML):
```
Negative: smiling, laughing, cartoonish, bright colors, low resolution,
morphing, blurry text, disfigured hands, extra fingers, flickering textures,
morphing clothes, overly vibrant colors, unbalanced layout, dark tone
```

### 7. Duration Planning
- **3–5 sec**: single action, single camera move
- **5–8 sec**: 2–3 action beats, camera can shift
- **8–12 sec**: full mini-sequence, setup -> action -> reaction
- Total scene duration = sum of shot durations. Keep under 15 sec per API request.

### 8. Style Prefix
The `style_prefix` is prepended automatically to every prompt. Put global visual style here — it should NOT contain action or camera directions:
```yaml
style_prefix: "3D cartoon for toddlers, Pixar-style, soft rounded shapes, warm pastel colors, big expressive eyes."
```

---

## Known Limitations

- **Color grading** can drift between cuts in multi-shot mode
- **Character consistency** relies on element reference images — provide 2–4 diverse angles
- **500 char limit** per shot prompt — be concise
- **File URLs expire** after 3 days — re-upload elements if pipeline resumes after a pause
- **Lip-sync** works but isn't perfect
- **Max 6 shots** per multi-shot request — split longer scenes into multiple API calls

---

## Modes of Operation

| Mode | Description |
|------|-------------|
| **Text-to-Video** | Generate video from a text prompt (single-shot) |
| **Image-to-Video** | Animate a static image (first/last frame) |
| **Multi-Shot** | Up to 6 shots with per-shot prompts and durations (our default) |

---

## Sources
- [Kling 3.0 Prompting Guide — fal.ai](https://blog.fal.ai/kling-3-0-prompting-guide/)
- [Kling 3.0 Review — Curious Refuge](https://curiousrefuge.com/blog/kling-30-review)
- [Kling 3.0 Features Guide — kling3.net](https://kling3.net/blog/kling-3-features-guide)
- [Kling 3.0 Prompt Guide — klingaio.com](https://klingaio.com/blogs/kling-3-prompt-guide)
- [Kling 3.0 vs 2.6 — imagine.art](https://www.imagine.art/blogs/kling-3-0-vs-kling-2-6-comparison)
- [Kling 3.0 Release Guide — gaga.art](https://gaga.art/blog/kling-3-0/)
- [Kling AI Negative Prompts — Pollo AI](https://pollo.ai/hub/kling-ai-best-negative-prompts)
