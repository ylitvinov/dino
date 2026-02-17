# Kling 3.0 — Complete Video Generation Guide

## Key Features

### Resolution & Duration
- **Native 4K** (3840x2160) at **60 fps** — broadcast and print-ready quality
- **Up to 15 seconds** of video with flexible duration (3–15s) instead of fixed presets
- Major improvement over Kling 2.6

### Multi-Shot Generation
- Up to **6 distinct camera cuts** in a single generation
- Per-shot control: duration, framing, camera movement
- Model understands cinematic language: profile shot, macro close-up, tracking shot, POV, shot-reverse-shot
- Smooth transitions with narrative continuity

### Native Audio & Dialogue
- Character **speech generation** directly in video
- **5 languages** supported: English, Chinese, Japanese, Korean, Spanish
- Up to **3-person dialogue** with accurate lip-sync
- Per-character control of tone, emotion, and accent

### Start/End Frame Control
- Specify **start and end frames** — model generates smooth interpolation
- Improved scene continuity compared to 2.6

### Character Consistency
- Face identity preserved through turns, expression changes, and scene transitions
- Multi-image references: supply multiple images for tighter style/identity lock

---

## Prompt Structure (The Key to Quality)

Think like a **director**, not a describer:

```
[Scene/Context] + [Character & Appearance] + [Action Timeline] +
[Camera Movement] + [Audio & Atmosphere] + [Technical Specs]
```

> A well-structured 200-word prompt will massively outperform a vague 20-word one.

### Example Prompt
```
A dimly lit jazz club in 1960s New York.

[Character A: A middle-aged Black man in a dark suit, deep baritone voice]:
"You always come back to this place." He sets down a glass of whiskey slowly.

Camera slowly dollies forward from a wide shot to a medium close-up.
Ambient jazz piano plays softly. Warm amber lighting with cigarette smoke haze.
```

---

## Tips & Best Practices

### 1. Describe Shots, Not Clips
Instead of a single long paragraph, **explicitly describe each shot** as part of a sequence. Label shots and describe framing, subject, and motion for each. This produces smoother transitions and intentional narrative flow.

### 2. Anchor Characters Early
Define key characters **at the very beginning** of the prompt and use **identical descriptions** across all shots. This locks appearance traits, objects, and environment stability.

### 3. Be Precise About Motion
- Describe both **subject actions** and **camera behavior**
- Use cinematic terms: `dolly push`, `whip-pan`, `crash zoom`, `tracking shot`, `shoulder-cam drift`, `snap focus`
- Camera movement should be **motivated**: follow a character, reveal information, emphasize emotion

### 4. Use Negative Prompts
The model defaults to "optimistic" outputs (smiling faces). For serious/gritty atmosphere, negative prompts are essential:

```
Negative: smiling, laughing, cartoonish, bright colors, low resolution,
morphing, blurry text, disfigured hands, extra fingers, flickering textures,
morphing clothes, overly vibrant colors, unbalanced layout, dark tone
```

### 5. Structure Dialogue Clearly
- Use unique labels: `[Speaker: Man]`, `[Character A: ...]`
- Bind each line of dialogue to a specific action
- Use temporal linking words: "Immediately," "Then," "Pause"
- This prevents the model from confusing speakers in lip-sync

### 6. Image-to-Video
- The input image acts as an **anchor**, not just a starting frame
- Prompt should describe **scene evolution** from that image
- Model preserves text, signage, and visual details from the source image well

### 7. Long Generations (10–15 sec)
- Describe **progression**: how action develops, how camera reacts
- Break into "beats": setup -> development -> moment's climax
- Leverage multi-beat performances with scene transitions

---

## Known Limitations

- **Color grading** can drift between cuts in multi-shot mode
- **Voice cloning** and character cloning are experimental — identity may drift
- **VFX editing** capabilities are limited
- **Lip-sync** works but isn't perfect — other tools may be more precise
- For serious production, best used as a **front-end generator** within a broader toolkit

---

## Modes of Operation

| Mode | Description |
|------|-------------|
| **Text-to-Video** | Generate video from a text prompt |
| **Image-to-Video** | Animate a static image |
| **Storyboard Mode** | Per-shot control with individual shot settings |
| **Multi-Shot** | Up to 6 shots with automatic transitions |

---

## Sources
- [Kling 3.0 Prompting Guide — fal.ai](https://blog.fal.ai/kling-3-0-prompting-guide/)
- [Kling 3.0 Review — Curious Refuge](https://curiousrefuge.com/blog/kling-30-review)
- [Kling 3.0 Features Guide — kling3.net](https://kling3.net/blog/kling-3-features-guide)
- [Kling 3.0 Prompt Guide — klingaio.com](https://klingaio.com/blogs/kling-3-prompt-guide)
- [Kling 3.0 vs 2.6 — imagine.art](https://www.imagine.art/blogs/kling-3-0-vs-kling-2-6-comparison)
- [Kling 3.0 Release Guide — gaga.art](https://gaga.art/blog/kling-3-0/)
- [Kling AI Negative Prompts — Pollo AI](https://pollo.ai/hub/kling-ai-best-negative-prompts)
