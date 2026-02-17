# Kling 3.0 — KIE.ai API Reference

Source: https://docs.kie.ai/market/kling/kling-3.0

## Overview

Kling 3.0 video generation model supporting single-shot and multi-shot creation with element references.

## Authentication

```
Authorization: Bearer YOUR_API_KEY
```

Key management: https://kie.ai/api-key

## Video Generation

**POST** `/api/v1/jobs/createTask`

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `model` | string | Must be `kling-3.0/video` |
| `input.prompt` | string | Video generation prompt |
| `input.sound` | boolean | Enable sound effects |
| `input.duration` | string | "3" through "15" |
| `input.mode` | string | "std" or "pro" |
| `input.multi_shots` | boolean | Single or multi-shot |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `callBackUrl` | string | Webhook for completion notifications |
| `image_urls` | array | First/last frame images |
| `aspect_ratio` | string | "16:9", "9:16", "1:1" (auto-detected if images provided) |
| `multi_prompt` | array | Required when `multi_shots: true`. `[{"prompt": str, "duration": int}]` |
| `kling_elements` | array | Element definitions for `@element_name` references |
| `cfg_scale` | float | Classifier-free guidance scale |

### Response

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "taskId": "task_kling-3.0_1765187774173"
  }
}
```

## Element References

Reference images/videos in prompts using `@element_name` syntax. Define in `kling_elements` array:

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Element identifier (matches `@name` in prompt) |
| `description` | string | Description of the element |
| `element_input_urls` | array | 2-4 image URLs (JPG/PNG, min 300x300px, max 10MB each) |
| `element_input_video_urls` | array | 1 video URL (MP4/MOV, max 50MB) |

Either `element_input_urls` or `element_input_video_urls`, not both.

## File Upload API

Base URL: `https://kieai.redpandaai.co`
Auth: Same Bearer token as main API.
Files are **temporary — auto-deleted after 3 days**.
Uploads are free.

### Method 1: File Stream Upload (recommended for local files)

**POST** `https://kieai.redpandaai.co/api/file-stream-upload`

Content-Type: `multipart/form-data`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | binary | yes | The file to upload |
| `uploadPath` | string | no | Custom storage path |
| `fileName` | string | no | Custom filename (random if omitted; overwrites if reused) |

### Method 2: Base64 Upload

**POST** `https://kieai.redpandaai.co/api/file-base64-upload`

Content-Type: `application/json`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base64Data` | string | yes | Base64-encoded file content |
| `uploadPath` | string | no | Custom storage path |
| `fileName` | string | no | Custom filename |

Best for files ≤10MB (base64 adds 33% overhead).

### Method 3: URL Upload

**POST** `https://kieai.redpandaai.co/api/file-url-upload`

Content-Type: `application/json`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `fileUrl` | string | yes | Remote file URL to fetch |
| `uploadPath` | string | no | Custom storage path |
| `fileName` | string | no | Custom filename |

Limit: 100MB, 30-second timeout.

### Upload Response

```json
{
  "success": true,
  "code": 200,
  "msg": "File uploaded successfully",
  "data": {
    "success": true,
    "fileName": "1771365803519-kbo99wcehlo.png",
    "filePath": "kieai/608626/elements/1771365803519-kbo99wcehlo.png",
    "downloadUrl": "https://tempfile.redpandaai.co/kieai/608626/elements/1771365803519-kbo99wcehlo.png",
    "fileSize": 1165742,
    "mimeType": "image/png",
    "uploadedAt": "2026-02-17T22:03:24.601Z"
  }
}
```

## Task Polling

**GET** `/api/v1/jobs/{task_id}`

Task statuses: `pending` → `processing` → `completed` | `failed`

## Best Practices

- Write specific prompts: motion, camera angles, composition
- Use high-quality reference images matching video style
- For multi-shot, align shot durations with total duration
- Use callbacks instead of polling in production
- Element names in `kling_elements` must match `@name` in prompts (without @)
