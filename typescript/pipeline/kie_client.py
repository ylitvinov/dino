"""Async HTTP client for the KIE.ai API.

Adapted from kling/pipeline/client.py for image-to-video clip generation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console

from pipeline.models import TaskStatus

logger = logging.getLogger(__name__)
_console = Console()

_DEFAULT_TIMEOUT = 60.0
_DOWNLOAD_TIMEOUT = 300.0


class KieApiError(Exception):
    """Raised when the KIE.ai API returns an error."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        self.status_code = status_code
        self.body = body
        super().__init__(message)


class KieClient:
    """Async client for KIE.ai Kling 3.0 API (image-to-video)."""

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
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if "json" in kwargs:
            _console.print(f"[cyan bold]── {method} {self.base_url}{url}[/cyan bold]")
            _console.print_json(json.dumps(kwargs["json"], ensure_ascii=False))
            _console.print()
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
        if "data" in data and isinstance(data["data"], dict):
            inner = data["data"]
            for key in ("task_id", "taskId"):
                if key in inner:
                    return inner[key]
        for key in ("task_id", "taskId"):
            if key in data:
                return data[key]
        raise KieApiError(f"Could not extract task_id from response: {data}", body=data)

    def _parse_task_status(self, data: dict) -> TaskStatus:
        task_data = data
        if "data" in data and isinstance(data["data"], dict):
            task_data = data["data"]

        task_id = task_data.get("taskId", task_data.get("task_id", ""))
        raw_state = task_data.get("state", task_data.get("status", "unknown"))
        state_map = {
            "waiting": "pending",
            "queuing": "pending",
            "generating": "processing",
            "success": "completed",
            "fail": "failed",
        }
        status = state_map.get(raw_state, raw_state)

        output_url: str | None = None
        result_json = task_data.get("resultJson")
        if isinstance(result_json, str) and result_json:
            try:
                result = json.loads(result_json)
                urls = result.get("resultUrls", [])
                if urls:
                    output_url = urls[0]
            except json.JSONDecodeError:
                pass
        if not output_url:
            output = task_data.get("output")
            if isinstance(output, dict):
                output_url = output.get("video_url") or output.get("image_url")
            elif isinstance(output, str) and output:
                output_url = output

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

    _UPLOAD_BASE_URL = "https://kieai.redpandaai.co"

    async def upload_file(self, file_path: str | Path) -> str:
        """Upload a local file to KIE.ai and return the file URL."""
        path = Path(file_path)
        if not path.exists():
            raise KieApiError(f"File not found: {path}")

        logger.info("Uploading %s (%.1f KB)", path, path.stat().st_size / 1024)

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
            ) as ul_client:
                with open(path, "rb") as f:
                    response = await ul_client.post(
                        f"{self._UPLOAD_BASE_URL}/api/file-stream-upload",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        files={"file": (path.name, f)},
                        data={"uploadPath": "elements"},
                    )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KieApiError(f"Upload failed for {path}: {exc}") from exc

        data = response.json()
        if not data.get("success") and data.get("code") != 200:
            raise KieApiError(f"Upload API error: {data.get('message', data)}", body=data)

        inner = data.get("data", {})
        file_url = inner.get("fileUrl") or inner.get("downloadUrl")
        if not file_url:
            raise KieApiError(f"No file URL in upload response: {data}", body=data)

        logger.info("Uploaded %s -> %s", path.name, file_url)
        return file_url

    async def create_image_to_video_task(
        self,
        image_url: str,
        prompt: str = "",
        duration: int = 5,
        mode: str = "pro",
        aspect_ratio: str = "9:16",
    ) -> str:
        """Create a Kling 3.0 image-to-video task.

        Args:
            image_url: URL of the uploaded image (used as first frame).
            prompt: Optional motion/style prompt.
            duration: Video duration in seconds (5 or 10).
            mode: Generation mode ("std" or "pro").
            aspect_ratio: Output aspect ratio.

        Returns:
            The task_id string for polling.
        """
        body: dict[str, Any] = {
            "model": "kling-3.0/video",
            "input": {
                "prompt": prompt,
                "image_urls": [image_url],
                "sound": False,
                "duration": str(duration),
                "aspect_ratio": aspect_ratio,
                "mode": mode,
                "multi_shots": False,
            },
        }

        logger.info("Creating image-to-video task: prompt=%r", prompt[:80] if prompt else "(empty)")
        response = await self._request("POST", "/api/v1/jobs/createTask", json=body)
        data = response.json()

        code = data.get("code")
        if code is not None and code != 200:
            error_msg = data.get("message", data.get("error", str(data)))
            raise KieApiError(f"API error (code={code}): {error_msg}", body=data)

        task_id = self._parse_task_id(data)
        logger.info("Image-to-video task created: %s", task_id)
        return task_id

    async def get_task_status(self, task_id: str) -> TaskStatus:
        """Get the current status of a task."""
        response = await self._request("GET", f"/api/v1/jobs/recordInfo?taskId={task_id}")
        data = response.json()
        return self._parse_task_status(data)

    async def wait_for_task(
        self,
        task_id: str,
        poll_interval: float = 10.0,
        max_wait: float = 300.0,
    ) -> TaskStatus:
        """Poll a task until it reaches a terminal state."""
        elapsed = 0.0
        status = None
        while elapsed < max_wait:
            status = await self.get_task_status(task_id)
            if status.is_done:
                return status
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise KieApiError(
            f"Task {task_id} did not complete within {max_wait}s. "
            f"Last status: {status.status if status else 'unknown'}"
        )

    async def download_file(self, url: str, output_path: str | Path) -> Path:
        """Download a file from a URL to a local path."""
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
