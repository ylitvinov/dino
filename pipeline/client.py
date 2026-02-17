"""Async HTTP client for the KIE.ai API.

Handles task creation, polling, and file downloads for Kling 3.0
video and image generation.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from pipeline.models import Element, TaskStatus

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0
_DOWNLOAD_TIMEOUT = 300.0


class KieApiError(Exception):
    """Raised when the KIE.ai API returns an error."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        self.status_code = status_code
        self.body = body
        super().__init__(message)


class KieClient:
    """Async client for KIE.ai Kling 3.0 API.

    Usage::

        async with KieClient(api_key="...") as client:
            task_id = await client.create_video_task(prompt="A cat on Mars")
            result = await client.wait_for_task(task_id)
            if result.is_success:
                await client.download_file(result.output_url, "output.mp4")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.kie.ai",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    async def __aenter__(self) -> KieClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request."""
        try:
            response = await self._client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise KieApiError(
                f"HTTP {exc.response.status_code}: {exc.response.text}",
                status_code=exc.response.status_code,
                body=exc.response.text,
            ) from exc
        except httpx.TimeoutException as exc:
            raise KieApiError(f"Request timeout: {exc}") from exc

    def _parse_task_id(self, data: dict) -> str:
        """Extract task_id from API response, handling nested structures."""
        # Try data.data.task_id / data.data.taskId (nested)
        if "data" in data and isinstance(data["data"], dict):
            inner = data["data"]
            for key in ("task_id", "taskId"):
                if key in inner:
                    return inner[key]

        # Try data.task_id / data.taskId (flat)
        for key in ("task_id", "taskId"):
            if key in data:
                return data[key]

        raise KieApiError(
            f"Could not extract task_id from response: {data}",
            body=data,
        )

    def _parse_task_status(self, data: dict) -> TaskStatus:
        """Parse a task status response into a TaskStatus object.

        Handles both nested (data.data.status) and flat (data.status) formats.
        """
        # Navigate to the task data
        task_data = data
        if "data" in data and isinstance(data["data"], dict):
            task_data = data["data"]

        task_id = task_data.get("taskId", task_data.get("task_id", ""))

        # KIE.ai uses "state" (success/fail/waiting/queuing/generating)
        # Map to our internal statuses (pending/processing/completed/failed)
        raw_state = task_data.get("state", task_data.get("status", "unknown"))
        state_map = {
            "waiting": "pending",
            "queuing": "pending",
            "generating": "processing",
            "success": "completed",
            "fail": "failed",
        }
        status = state_map.get(raw_state, raw_state)

        # Extract output URL from resultJson or output field
        output_url: str | None = None
        result_json = task_data.get("resultJson")
        if isinstance(result_json, str) and result_json:
            import json as _json
            try:
                result = _json.loads(result_json)
                urls = result.get("resultUrls", [])
                if urls:
                    output_url = urls[0]
            except _json.JSONDecodeError:
                pass
        if not output_url:
            output = task_data.get("output")
            if isinstance(output, dict):
                output_url = output.get("video_url") or output.get("image_url")
            elif isinstance(output, str) and output:
                output_url = output

        # Extract error
        error: str | None = None
        err = task_data.get("error")
        if isinstance(err, dict):
            error = err.get("message")
        elif isinstance(err, str) and err:
            error = err

        return TaskStatus(
            task_id=task_id,
            status=status,
            output_url=output_url,
            error=error,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_video_task(
        self,
        prompt: str,
        negative_prompt: str = "",
        elements: list[Element] | None = None,
        duration: int = 5,
        mode: str = "pro",
        aspect_ratio: str = "16:9",
        cfg_scale: float = 0.5,
    ) -> str:
        """Create a Kling 3.0 video generation task.

        Args:
            prompt: The video generation prompt.
            negative_prompt: Things to avoid in the generated video.
            elements: Optional list of Element objects with reference images.
            duration: Video duration in seconds (5 or 10).
            mode: Generation mode ("std" or "pro").
            aspect_ratio: Output aspect ratio.
            cfg_scale: Classifier-free guidance scale.

        Returns:
            The task_id string for polling.

        Raises:
            KieApiError: On API errors.
        """
        kling_elements = []
        if elements:
            for el in elements:
                if el.image_urls:
                    kling_elements.append({
                        "name": el.name,
                        "description": el.description,
                        "element_input_urls": el.image_urls,
                    })

        body: dict[str, Any] = {
            "model": "kling-3.0/video",
            "task_type": "video_generation",
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "duration": str(duration),
                "mode": mode,
                "aspect_ratio": aspect_ratio,
                "cfg_scale": cfg_scale,
                "multi_shots": False,
                "sound": True,
            },
            "config": {
                "webhook_config": {
                    "endpoint": "",
                    "secret": "",
                },
            },
        }

        if kling_elements:
            body["input"]["kling_elements"] = kling_elements

        logger.info("Creating video task: prompt=%r, elements=%d", prompt[:80], len(kling_elements))
        response = await self._request("POST", "/api/v1/jobs/createTask", json=body)
        data = response.json()

        # Check for API-level errors
        code = data.get("code")
        if code is not None and code != 200:
            error_msg = data.get("message", data.get("error", str(data)))
            raise KieApiError(f"API error (code={code}): {error_msg}", body=data)

        task_id = self._parse_task_id(data)
        logger.info("Video task created: %s", task_id)
        return task_id

    async def create_multi_shot_task(
        self,
        shots: list[dict],
        negative_prompt: str = "",
        elements: list[Element] | None = None,
        mode: str = "pro",
        aspect_ratio: str = "16:9",
        cfg_scale: float = 0.5,
    ) -> str:
        """Create a Kling 3.0 multi-shot video generation task.

        Submits multiple shots as a single request for visual continuity.

        Args:
            shots: List of {"prompt": str, "duration": int} dicts.
            negative_prompt: Things to avoid in the generated video.
            elements: Optional list of Element objects with reference images.
            mode: Generation mode ("std" or "pro").
            aspect_ratio: Output aspect ratio.
            cfg_scale: Classifier-free guidance scale.

        Returns:
            The task_id string for polling.

        Raises:
            ValueError: If shots exceed limits (>6 shots or >15s total).
            KieApiError: On API errors.
        """
        if len(shots) > 6:
            raise ValueError(f"Multi-shot supports max 6 shots, got {len(shots)}")
        total_duration = sum(s["duration"] for s in shots)
        if total_duration > 15:
            raise ValueError(f"Multi-shot supports max 15s total, got {total_duration}s")

        kling_elements = []
        if elements:
            for el in elements:
                if el.image_urls:
                    kling_elements.append({
                        "name": el.name,
                        "description": el.description,
                        "element_input_urls": el.image_urls,
                    })

        multi_prompt = [
            {"prompt": s["prompt"], "duration": s["duration"]}
            for s in shots
        ]

        body: dict[str, Any] = {
            "model": "kling-3.0/video",
            "task_type": "video_generation",
            "input": {
                "multi_shots": True,
                "multi_prompt": multi_prompt,
                "negative_prompt": negative_prompt,
                "duration": str(total_duration),
                "mode": mode,
                "aspect_ratio": aspect_ratio,
                "cfg_scale": cfg_scale,
                "sound": True,
            },
            "config": {
                "webhook_config": {
                    "endpoint": "",
                    "secret": "",
                },
            },
        }

        if kling_elements:
            body["input"]["kling_elements"] = kling_elements

        logger.info(
            "Creating multi-shot task: %d shots, %ds total, elements=%d",
            len(shots), total_duration, len(kling_elements),
        )
        response = await self._request("POST", "/api/v1/jobs/createTask", json=body)
        data = response.json()

        code = data.get("code")
        if code is not None and code != 200:
            error_msg = data.get("message", data.get("error", str(data)))
            raise KieApiError(f"API error (code={code}): {error_msg}", body=data)

        task_id = self._parse_task_id(data)
        logger.info("Multi-shot task created: %s", task_id)
        return task_id

    async def create_image_task(
        self,
        prompt: str,
        negative_prompt: str = "",
        aspect_ratio: str = "16:9",
    ) -> str:
        """Create a Kling 3.0 image generation task.

        Args:
            prompt: The image generation prompt.
            negative_prompt: Things to avoid.
            aspect_ratio: Output aspect ratio.

        Returns:
            The task_id string for polling.

        Raises:
            KieApiError: On API errors.
        """
        body: dict[str, Any] = {
            "model": "kling-3.0/image",
            "task_type": "image_generation",
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "aspect_ratio": aspect_ratio,
            },
        }

        logger.info("Creating image task: prompt=%r", prompt[:80])
        response = await self._request("POST", "/api/v1/jobs/createTask", json=body)
        data = response.json()

        code = data.get("code")
        if code is not None and code != 200:
            error_msg = data.get("message", data.get("error", str(data)))
            raise KieApiError(f"API error (code={code}): {error_msg}", body=data)

        task_id = self._parse_task_id(data)
        logger.info("Image task created: %s", task_id)
        return task_id

    async def get_task_status(self, task_id: str) -> TaskStatus:
        """Get the current status of a task.

        Args:
            task_id: The task identifier.

        Returns:
            TaskStatus with current state and output URL if completed.

        Raises:
            KieApiError: On API errors.
        """
        response = await self._request("GET", f"/api/v1/jobs/recordInfo?taskId={task_id}")
        data = response.json()
        return self._parse_task_status(data)

    async def wait_for_task(
        self,
        task_id: str,
        poll_interval: float = 10.0,
        max_wait: float = 300.0,
    ) -> TaskStatus:
        """Poll a task until it reaches a terminal state.

        Args:
            task_id: The task identifier.
            poll_interval: Seconds between polls.
            max_wait: Maximum seconds to wait before raising an error.

        Returns:
            Final TaskStatus.

        Raises:
            KieApiError: If max_wait is exceeded or API errors occur.
        """
        elapsed = 0.0
        while elapsed < max_wait:
            status = await self.get_task_status(task_id)
            logger.debug("Task %s: status=%s (%.0fs elapsed)", task_id, status.status, elapsed)

            if status.is_done:
                return status

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise KieApiError(
            f"Task {task_id} did not complete within {max_wait}s. "
            f"Last status: {status.status}"
        )

    async def download_file(self, url: str, output_path: str | Path) -> Path:
        """Download a file from a URL to a local path.

        Args:
            url: The URL to download from.
            output_path: Local file path to save to.

        Returns:
            The resolved output path.

        Raises:
            KieApiError: On download errors.
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Downloading %s -> %s", url, output)
        try:
            async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as dl_client:
                async with dl_client.stream("GET", url) as response:
                    response.raise_for_status()
                    with open(output, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
        except httpx.HTTPError as exc:
            raise KieApiError(f"Download failed for {url}: {exc}") from exc

        logger.info("Downloaded: %s (%.1f KB)", output, output.stat().st_size / 1024)
        return output
