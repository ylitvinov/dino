> ## Documentation Index
> Fetch the complete documentation index at: https://docs.kie.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Kling 3.0

> Generate high-quality videos with advanced multi-shot capabilities and element references using Kling 3.0 AI model

## Overview

Kling 3.0 is an advanced video generation model that supports both single-shot and multi-shot video creation with element references. It offers two generation modes (standard and pro) with different resolution options, and supports sound effects for enhanced video output.

## Key Features

* **Dual Generation Modes**: Choose between `std` (standard resolution) and `pro` (higher resolution) modes
* **Multi-Shot Support**: Create videos with multiple shots, each with its own prompt and duration
* **Element References**: Reference images or videos in your prompts using `@element_name` syntax
* **Sound Effects**: Optional sound effects to enhance video output
* **Flexible Aspect Ratios**: Support for 16:9, 9:16, and 1:1 aspect ratios
* **Configurable Duration**: Video duration from 3 to 15 seconds

## Single-Shot vs Multi-Shot Mode

### Single-Shot Mode (`multi_shots: false`)

* Uses the main `prompt` field for video generation
* Supports first and last frame images via `image_urls`
* Sound effects are optional

### Multi-Shot Mode (`multi_shots: true`)

* Uses `multi_prompt` array to define multiple shots
* Each shot has its own prompt and duration (1-12 seconds)
* Only supports first frame image (via `image_urls[0]`)
* Sound effects default to enabled

## Aspect Ratio Auto-Adaptation

When you provide `image_urls` (first or last frame images), the `aspect_ratio` parameter becomes optional. The system will automatically adapt the aspect ratio based on the uploaded images, so you don't need to specify it manually.

<Tip>
  If you upload reference images, you can omit the `aspect_ratio` parameter and let the system automatically match the aspect ratio of your images.
</Tip>

## Element References

You can reference images or videos in your prompts using the `@element_name` syntax. Define elements in the `kling_elements` array:

* **Image Elements**: 2-4 image URLs (JPG/PNG, at least 300\*300px, max 10MB each)
* **Video Elements**: 1 video URL (MP4/MOV, max 50MB)

<Tip>
  Use descriptive element names and ensure the element name in `kling_elements` matches the name used in your prompt (without the @ symbol).
</Tip>

## File Upload Requirements

Before using element references, upload your image or video files:

<Steps>
  <Step title="Upload Files">
    Use the File Upload API to upload your source images or videos.

    <Card title="File Upload API" icon="upload" href="/file-upload-api/quickstart">
      Learn how to upload files and get file URLs
    </Card>
  </Step>

  <Step title="Get File URLs">
    After upload, you'll receive file URLs that you can use in `element_input_urls` or `element_input_video_urls`.
  </Step>
</Steps>

<Warning>
  * Image formats: JPG, PNG (max 10MB per file, 2-4 files per element)
  * Video formats: MP4, MOV (max 50MB per file, 1 file per element)
  * Ensure file URLs are accessible and not expired
</Warning>

## Usage Examples

### Single-Shot Video with Element Reference

```json  theme={null}
{
  "model": "kling-3.0",
  "input": {
    "prompt": "In a bright rehearsal room, sunlight streams through the window @element_dog",
    "image_urls": [
      "https://static.aiquickdraw.com/tools/example/1764851002741_i0lEiI8I.png"
    ],
    "sound": true,
    "duration": "5",
    "aspect_ratio": "16:9",
    "mode": "pro",
    "multi_shots": false,
    "kling_elements": [
      {
        "name": "element_dog",
        "description": "dog",
        "element_input_urls": [
          "https://tempfileb.aiquickdraw.com/kieai/market/1770361808044_4RfUUJrI.jpeg",
          "https://tempfileb.aiquickdraw.com/kieai/market/1770361848336_ABQqRHBi.png"
        ]
      }
    ]
  }
}
```

### Multi-Shot Video

```json  theme={null}
{
  "model": "kling-3.0",
  "input": {
    "multi_shots": true,
    "image_urls": [
      "https://static.aiquickdraw.com/tools/example/1764851002741_i0lEiI8I.png"
    ],
    "duration": "5",
    "aspect_ratio": "16:9",
    "mode": "pro",
    "multi_prompt": [
      {
        "prompt": "a happy dog in running @element_dog",
        "duration": 3
      },
      {
        "prompt": "a happy dog play with a cat @element_cat",
        "duration": 3
      }
    ],
    "kling_elements": [
      {
        "name": "element_cat",
        "description": "cat",
        "element_input_video_urls": [
          "https://your-cdn.com/element_video.mp4"
        ]
      },
      {
        "name": "element_dog",
        "description": "dog",
        "element_input_urls": [
          "https://tempfileb.aiquickdraw.com/kieai/market/1770361808044_4RfUUJrI.jpeg"
        ]
      }
    ]
  }
}
```

## Query Task Status

After submitting a task, use the unified query endpoint to check progress and retrieve results:

<Card title="Get Task Details" icon="magnifying-glass" href="/market/common/get-task-detail">
  Learn how to query task status and retrieve generation results
</Card>

<Tip>
  For production use, we recommend using the `callBackUrl` parameter to receive automatic notifications when generation completes, rather than polling the status endpoint.
</Tip>

## Best Practices

* **Prompt Writing**: Be specific and descriptive in your prompts. Include details about motion, camera angles, and scene composition
* **Element Usage**: Use high-quality reference images/videos for better results. Ensure elements match the style and theme of your video
* **Duration Planning**: For multi-shot videos, plan your shot durations to match the total video duration
* **Mode Selection**: Use `pro` mode for final output when quality is important, and `std` mode for faster iterations
* **Sound Effects**: Enable sound effects for more immersive videos, especially for action or dynamic scenes

## Related Resources

<CardGroup cols={2}>
  <Card title="Market Overview" icon="store" href="/market/quickstart">
    Explore all available models
  </Card>

  <Card title="Common API" icon="gear" href="/common-api/get-account-credits">
    Check credits and account usage
  </Card>
</CardGroup>


## OpenAPI

````yaml market/kling/kling-3.0.json post /api/v1/jobs/createTask
openapi: 3.0.0
info:
  title: Kling API
  description: kie.ai Kling API Documentation - Kling 3.0 Video Generation
  version: 1.0.0
  contact:
    name: Technical Support
    email: support@kie.ai
servers:
  - url: https://api.kie.ai
    description: API Server
security:
  - BearerAuth: []
paths:
  /api/v1/jobs/createTask:
    post:
      summary: Generate videos using kling-3.0
      operationId: kling-3.0
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - model
              properties:
                model:
                  type: string
                  enum:
                    - kling-3.0/video
                  default: kling-3.0/video
                  description: |-
                    The model name to use for generation. Required field.

                    - Must be `kling-3.0/video` for this endpoint
                  example: kling-3.0/video
                callBackUrl:
                  type: string
                  format: uri
                  description: >-
                    The URL to receive generation task completion updates.
                    Optional but recommended for production use.


                    - System will POST task status and results to this URL when
                    generation completes

                    - Callback includes generated content URLs and task
                    information

                    - Your callback endpoint should accept POST requests with
                    JSON payload containing results

                    - Alternatively, use the Get Task Details endpoint to poll
                    task status

                    - To ensure callback security, see [Webhook Verification
                    Guide](/common-api/webhook-verification) for signature
                    verification implementation
                  example: https://your-domain.com/api/callback
                input:
                  type: object
                  description: Input parameters for the generation task
                  properties:
                    prompt:
                      type: string
                      description: >-
                        Video generation prompt. Takes effect when multi_shots
                        is false.
                      example: >-
                        In a bright rehearsal room, sunlight streams through the
                        window @element_dog
                    image_urls:
                      type: array
                      items:
                        type: string
                        format: uri
                      description: >-
                        First and last frame image URLs. Required when elements
                        are referenced in the prompt (using @element_name
                        syntax). When multi_shots is false: if length is 2,
                        index 0 is the first frame and index 1 is the last
                        frame; if length is 1, the array item serves as the
                        first frame. When multi_shots is true: only the first
                        frame is supported. Only JPG, JPEG, PNG formats are
                        supported.
                      example:
                        - >-
                          https://static.aiquickdraw.com/tools/example/1764851002741_i0lEiI8I.png
                    sound:
                      type: boolean
                      description: >-
                        Whether to enable sound effects. true enables sound
                        effects, false disables them. When multi_shots is true,
                        this field must be true.
                      default: false
                      example: true
                    duration:
                      type: string
                      description: >-
                        Total video duration in seconds. Integer value, range: 3
                        to 15.
                      enum:
                        - '3'
                        - '4'
                        - '5'
                        - '6'
                        - '7'
                        - '8'
                        - '9'
                        - '10'
                        - '11'
                        - '12'
                        - '13'
                        - '14'
                        - '15'
                      default: '5'
                      example: '5'
                    aspect_ratio:
                      type: string
                      description: >-
                        Video aspect ratio. Options: 16:9, 9:16, 1:1. When your
                        input does not contain reference images (image_urls),
                        the default is 1:1 if aspect_ratio is not passed. When
                        your input contains the first frame image, the
                        aspect_ratio parameter is invalid (or can be left
                        empty), and the result will only follow the aspect ratio
                        of the first frame image.
                      enum:
                        - '16:9'
                        - '9:16'
                        - '1:1'
                      default: '1:1'
                      example: '1:1'
                    mode:
                      type: string
                      description: >-
                        Generation mode. std has standard resolution, pro has
                        higher resolution.
                      enum:
                        - std
                        - pro
                      default: pro
                      example: pro
                    multi_shots:
                      type: boolean
                      description: >-
                        Whether to use multi-shot mode. true enables multi-shot
                        mode, false enables single-shot mode.
                      default: false
                      example: false
                    multi_prompt:
                      type: array
                      description: >-
                        Shot prompts. Takes effect when multi_shots is true.
                        Used to describe the text and duration of each shot.
                        Each shot duration is 1-12 seconds. If you need to use
                        elements, add them after the prompt.
                      items:
                        type: object
                        properties:
                          prompt:
                            type: string
                            description: >-
                              Prompt text for this shot. Each prompt in the
                              group is limited to 500 characters.
                            example: a happy dog in running @element_dog
                          duration:
                            type: integer
                            description: 'Duration of this shot in seconds. Range: 1-12.'
                            minimum: 1
                            maximum: 12
                            example: 3
                        required:
                          - prompt
                          - duration
                      example:
                        - prompt: a happy dog in running @element_dog
                          duration: 3
                        - prompt: a happy dog play with a cat @element_cat
                          duration: 3
                    kling_elements:
                      type: array
                      description: >-
                        Referenced elements. Detailed information about elements
                        referenced in the prompt.
                      items:
                        type: object
                        properties:
                          name:
                            type: string
                            description: >-
                              Element name, used in prompt with @ prefix (e.g.,
                              @element_dog)
                            example: element_dog
                          description:
                            type: string
                            description: Element description
                            example: dog
                          element_input_urls:
                            type: array
                            items:
                              type: string
                              format: uri
                            description: >-
                              Image URLs for the element. 2-4 URLs required.
                              Accepted formats: JPG, PNG. At least 300*300px.
                              Maximum file size: 10MB per image.
                            example:
                              - >-
                                https://tempfileb.aiquickdraw.com/kieai/market/1770361808044_4RfUUJrI.jpeg
                              - >-
                                https://tempfileb.aiquickdraw.com/kieai/market/1770361848336_ABQqRHBi.png
                          element_input_video_urls:
                            type: array
                            items:
                              type: string
                              format: uri
                            description: >-
                              Video URL for the element. 1 URL required.
                              Accepted formats: MP4, MOV. Maximum file size:
                              50MB.
                            example:
                              - https://your-cdn.com/element_video.mp4
                        required:
                          - name
                          - description
                      example:
                        - name: element_dog
                          description: dog
                          element_input_urls:
                            - >-
                              https://tempfileb.aiquickdraw.com/kieai/market/1770361808044_4RfUUJrI.jpeg
                            - >-
                              https://tempfileb.aiquickdraw.com/kieai/market/1770361848336_ABQqRHBi.png
                        - name: element_cat
                          description: cat
                          element_input_video_urls:
                            - https://your-cdn.com/element_video.mp4
                  required:
                    - prompt
                    - sound
                    - duration
                    - mode
                    - multi_shots
                    - multi_prompt
            example:
              model: kling-3.0/video
              callBackUrl: https://your-domain.com/api/callback
              input:
                prompt: >-
                  In a bright rehearsal room, sunlight streams through the
                  window @element_dog
                image_urls:
                  - >-
                    https://static.aiquickdraw.com/tools/example/1764851002741_i0lEiI8I.png
                sound: true
                duration: '5'
                aspect_ratio: '16:9'
                mode: pro
                multi_shots: false
                multi_prompt:
                  - prompt: a happy dog in running @element_dog
                    duration: 3
                  - prompt: a happy dog play with a cat @element_cat
                    duration: 3
                kling_elements:
                  - name: element_dog
                    description: dog
                    element_input_urls:
                      - >-
                        https://tempfileb.aiquickdraw.com/kieai/market/1770361808044_4RfUUJrI.jpeg
                      - >-
                        https://tempfileb.aiquickdraw.com/kieai/market/1770361848336_ABQqRHBi.png
                  - name: element_cat
                    description: cat
                    element_input_video_urls:
                      - https://your-cdn.com/element_video.mp4
      responses:
        '200':
          description: Request successful
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/ApiResponse'
                  - type: object
                    properties:
                      data:
                        type: object
                        properties:
                          taskId:
                            type: string
                            description: >-
                              Task ID, can be used with Get Task Details
                              endpoint to query task status
                            example: task_kling-3.0_1765187774173
              example:
                code: 200
                msg: success
                data:
                  taskId: task_kling-3.0_1765187774173
        '500':
          $ref: '#/components/responses/Error'
components:
  schemas:
    ApiResponse:
      type: object
      properties:
        code:
          type: integer
          enum:
            - 200
            - 401
            - 402
            - 404
            - 422
            - 429
            - 455
            - 500
            - 501
            - 505
          description: >-
            Response status code


            - **200**: Success - Request has been processed successfully

            - **401**: Unauthorized - Authentication credentials are missing or
            invalid

            - **402**: Insufficient Credits - Account does not have enough
            credits to perform the operation

            - **404**: Not Found - The requested resource or endpoint does not
            exist

            - **422**: Validation Error - The request parameters failed
            validation checks

            - **429**: Rate Limited - Request limit has been exceeded for this
            resource

            - **455**: Service Unavailable - System is currently undergoing
            maintenance

            - **500**: Server Error - An unexpected error occurred while
            processing the request

            - **501**: Generation Failed - Content generation task failed

            - **505**: Feature Disabled - The requested feature is currently
            disabled
        msg:
          type: string
          description: Response message, error description when failed
          example: success
  responses:
    Error:
      description: Server Error
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: API Key
      description: >-
        All APIs require authentication via Bearer Token.


        Get API Key:

        1. Visit [API Key Management Page](https://kie.ai/api-key) to get your
        API Key


        Usage:

        Add to request header:

        Authorization: Bearer YOUR_API_KEY


        Note:

        - Keep your API Key secure and do not share it with others

        - If you suspect your API Key has been compromised, reset it immediately
        in the management page

````