# Kling 3.0 — Video Generation Guide

## Key Features

### Resolution & Duration
- **Native 4K** (3840x2160) at **60 fps**
- **3–15 seconds** per generation, flexible duration
- Two modes: `std` (standard) and `pro` (higher resolution)

### Multi-Shot Generation
- Up to **6 distinct shots** in a single generation
- Per-shot control: `prompt` + `duration` (1–12 sec each)
- Model understands cinematic language natively

### Element References
- Reference characters/backgrounds via `@ElementName` syntax in prompts
- Elements = 2–4 reference images (JPG/PNG, min 300x300px, max 10MB each)
- Elements are passed per-request via `kling_elements` array (not stored server-side)
- File URLs expire after 3 days — re-upload if expired
- Supports tracking up to 3 independent characters in the same scene

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
| `style_prefix` | top | Prepended to every shot prompt. Defines visual style only — no action/camera. |
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

Think like a **Director of Photography**, not a photographer. Write prompts like scene directions, not object inventories. Prompts referencing cinematic concepts (coverage, composition, pacing) consistently outperform purely visual attribute prompts.

### The formula

```
[Camera type + movement], [Subject @Element doing action in sequence], [Technical: DOF, lighting, composition]
```

Optimal length: **1–3 rich sentences** (under ~40 words). Must fit within **500 characters**.

### Camera abbreviations

| Abbreviation | Meaning |
|-------------|---------|
| `EWS` | Extreme wide shot |
| `WS` | Wide shot |
| `MS` | Medium shot |
| `CU` | Close-up |
| `ECU` | Extreme close-up |
| `POV` | Point of view |

### Camera movement vocabulary

Always describe camera movement **in relation to the subject** — "camera follows" is better than "camera moves right." Without camera direction, Kling defaults to static framing.

**Tracking & dolly:**
- `slow dolly push` / `dolly pull` — forward/backward on rails
- `tracking shot` — camera follows subject laterally
- `truck left` / `truck right` — lateral movement alongside subject
- `steadicam` — smooth following movement
- `orbit` — camera circles around subject

**Speed & energy:**
- `whip-pan` — fast horizontal rotation
- `crash zoom` — aggressive fast zoom
- `snap focus` — instant focus shift
- `handheld` / `shoulder-cam drift` — organic shake/drift

**Vertical & dramatic:**
- `crane shot` — vertical camera movement
- `low-angle tracking` — heroic/imposing perspective
- `dolly zoom` — dramatic vertigo effect (Hitchcock)
- `FPV` — first-person view, high-energy immersive

**Lens language** (the model responds to these):
- `"Macro 85mm lens"` — tight detail, shallow depth
- `"Wide-angle steadicam"` — smooth immersive movement
- `anamorphic` — cinematic widescreen look

### Element references

Use `@ElementName` inline wherever the element appears in the action:

```yaml
- prompt: "MS on @Topa sleeping curled on a big leaf. Warm sunbeam reaches his face."
```

The `@Name` must match a name from the scene's `kling_elements` list. Do NOT re-describe the character's appearance — the reference images handle identity. Focus on **what the character does**.

### Example shot prompts

**Establishing shot (no character):**
```yaml
- prompt: "EWS, slow dolly push. @Valley at sunrise — morning mist drifting low, volumetric light rays through ferns, pink-orange sky. Winding river reflects warm colors. Deep focus, cinematic composition."
  duration: 5
```

**Character action (sequential beats):**
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

### 1. Sequence Actions as Temporal Beats

The "secret sauce" of good prompts. Don't describe static states — describe how action unfolds over time:

```
"First [A], then [B], finally [C]"
```

For a 5-second shot, describe **2–3 beats** in order:
```
He scrunches nose, yawns wide showing tiny tongue, opens big brown eyes, stretches chubby legs one by one.
```

Use temporal connectors: "Immediately," "Then," "Pause," "Suddenly," "Meanwhile."

### 2. Camera Direction Is Near-Mandatory

Without explicit camera instructions, Kling defaults to static framing. Always specify:
- **What** the camera does (dolly, track, orbit, static)
- **How** it relates to the subject (follows, reveals, pushes toward)
- **Why** — motivated by character action or emotion

Bad: `"A cheetah in a field"` (static, no motion)
Good: `"MS tracking shot, camera follows @Topa as he trots through ferns, low angle, golden rim light"`

### 3. Anchor Characters via Elements

Don't re-describe characters in every prompt. The `@ElementName` reference + uploaded images handle identity. Focus the prompt on **what the character does**. Mention distinctive features only for emphasis when they're part of the action (e.g. "orange frill wiggles").

Provide **2–4 reference images from diverse angles** per element for best consistency.

### 4. Use Specific Lighting, Not Abstract Descriptors

Bad: `"dramatic lighting"`
Good: Name the actual light source and quality:

- `golden rim light`, `warm sunbeam`, `volumetric light rays through ferns`
- `sunrise golden hour`, `soft bounce light`
- `neon signs`, `candlelight`, `flickering fluorescent tubes`
- `three-point lighting`, `warm rim lighting`

### 5. End Prompts with Technical Depth Cues

Technical details as the last clause improve quality:

| Shot type | Recommended trailing details |
|-----------|------------------------------|
| Close-up | `Shallow DOF, bokeh background, golden rim light` |
| Wide/establishing | `Deep focus, cinematic composition` |
| Character highlight | `Golden rim light outlines body` |
| Atmospheric | `Volumetric light rays, soft-focused background` |
| Action | `Motion blur, rack focus` |

### 6. Describe Physics Even in Cartoon

The model respects physical behavior. Even for Pixar-style animation, describe **how things move physically** — fabric swaying, water splashing, objects bouncing, dust rising, frill wiggling. This produces more believable animation.

### 7. Duration Planning

| Duration | Complexity | Example |
|----------|-----------|---------|
| 3–5 sec | Single action, single camera move | Character wakes up |
| 5–8 sec | 2–3 action beats, camera can shift | Character wakes up and looks around |
| 8–12 sec | Setup → action → reaction | Character wakes up, notices something, reacts |

- Total scene duration = sum of shot durations. **Max 15 sec per API request.**
- 4–6 shots for 10–15 sec is optimal pacing.
- More than 6 shots in under 10 sec feels rushed — avoid.

### 8. Multi-Shot Narrative Coherence

- Use an **escalation pattern**: establish scene → introduce action → build intensity → climax
- Alternate between **wide shots and close-ups** for visual variety
- Keep element references **consistent** across all shots — never switch to pronouns
- Close with **directional movement** (toward/away from camera) for pacing closure

### 9. Style Prefix

The `style_prefix` is prepended automatically to every prompt. Put **only** global visual style here — no action or camera directions:

```yaml
style_prefix: "3D cartoon for toddlers, Pixar-style, soft rounded shapes, warm pastel colors, big expressive eyes."
```

Effective Pixar-style keywords: `soft rounded shapes`, `warm pastel colors`, `big expressive eyes`, `slightly plastic sheen`, `soft fabric textures`, `smooth subsurface scattering`, `exaggerated expressive features`.

### 10. Negative Prompts

Configured at API level, not in scenario YAML. Select only the terms relevant to what you want to suppress.

**Recommended for Pixar-style 3D animation:**
```
low quality, blurry, morphing, distorted faces, extra fingers, flickering textures,
morphing clothes, disfigured, ugly, dark tone, low resolution
```

**Do NOT include in negatives for cartoon content:**
- `cartoonish` — conflicts with intended style
- `bright colors` — we intentionally use saturated palettes
- `photorealistic` — should not appear in prompts at all for Pixar style

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| No camera direction | Always start with camera type + movement |
| Re-describing character appearance | Use `@Element`, focus on actions |
| Vague motion ("moves," "goes") | Use cinematic verbs: `trots`, `dashes`, `wobbles` |
| Static description, no timeline | Sequence beats: "First A, then B, finally C" |
| Abstract lighting ("dramatic") | Name the light source: `golden rim light`, `warm sunbeam` |
| Pronoun drift ("he... then he...") | Use character labels or `@Element` consistently |
| Too many shots < 10 sec | Keep 4–6 shots per 10–15 sec |
| Prompt over 500 chars | Trim descriptions, rely on style_prefix + elements |
| Complex body contact (hugging) | Produces melting artifacts ~30–40% of the time; avoid or simplify |
| Counting specific objects | AI struggles with exact quantities; avoid relying on this |

---

## Known Limitations

- **Color grading** can drift between cuts in multi-shot mode
- **Character consistency** relies on element reference images — provide 2–4 diverse angles
- **500 char limit** per shot prompt — be concise
- **File URLs expire** after 3 days — re-upload elements if pipeline resumes after a pause
- **Lip-sync** works but isn't perfect
- **Max 6 shots** per multi-shot request — split longer scenes into multiple API calls
- **Body contact** (hugging, handshaking) often causes "melting" artifacts
- **Text rendering** in video remains unstable
- **Counting** — AI struggles with specific quantities of objects

---

## Modes of Operation

| Mode | Description |
|------|-------------|
| **Text-to-Video** | Generate video from a text prompt (single-shot) |
| **Image-to-Video** | Animate a static image (first/last frame). Image acts as anchor; prompt should describe scene evolution from it. |
| **Multi-Shot** | Up to 6 shots with per-shot prompts and durations (our default) |

---

## Sources
- [Kling 3.0 Prompting Guide — fal.ai](https://blog.fal.ai/kling-3-0-prompting-guide/) — Most detailed single source on prompt structure & dialogue
- [Kling 3.0 Prompt Guide — klingaio.com](https://klingaio.com/blogs/kling-3-prompt-guide) — Master formula & action timeline
- [Kling 3.0 Prompts Guide — BasedLabs](https://www.basedlabs.ai/articles/kling-3-prompts-guide) — Camera terminology & pre-generation checklist
- [Kling 3.0 Prompt Guide — imagine.art](https://www.imagine.art/blogs/kling-3-0-prompt-guide) — Multi-shot examples & dialogue
- [Kling 3.0 Prompting Guide — Glif](https://glif.app/use-cases/kling-3-prompting-guide) — Texture, color/mood language, weak vs strong prompts
- [Kling 3.0 50+ Examples — kling3.xyz](https://www.kling3.xyz/prompt-guide.html) — Motion keywords & negative prompt categories
- [Kling 3.0 Features Guide — kling3.net](https://kling3.net/blog/kling-3-features-guide) — Feature overview
- [Kling 3.0 User Guide — Higgsfield](https://higgsfield.ai/blog/Kling-3.0-is-on-Higgsfield-User-Guide-AI-Video-Generation) — Multi-scene workflow
- [Animation Styles for Video Gen — Segmind](https://blog.segmind.com/best-animation-styles-for-video-generation-kling-ai-runway-minimax-and-hunyuan/) — 3D/Pixar animation keywords
- [Kling 3.0 Review — Curious Refuge](https://curiousrefuge.com/blog/kling-30-review)
- [Kling 3.0 vs 2.6 — imagine.art](https://www.imagine.art/blogs/kling-3-0-vs-kling-2-6-comparison)
- [Kling AI Negative Prompts — Pollo AI](https://pollo.ai/hub/kling-ai-best-negative-prompts)
