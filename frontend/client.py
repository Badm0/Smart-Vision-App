"""Thin HTTP client for the Smart Vision backend."""
from __future__ import annotations

from typing import Iterator

import requests


class ApiError(RuntimeError):
    """Raised with a human-readable message when the backend rejects a request."""


class SmartVisionClient:
    def __init__(self, base_url: str, public_url: str | None = None, timeout: float = 3.0) -> None:
        self.base = base_url.rstrip("/")
        # URL the *browser* uses to reach the API (may differ from `base` behind a proxy/Docker).
        self.public = (public_url or base_url).rstrip("/")
        self.timeout = timeout
        self._http = requests.Session()

    def _get_json(self, path: str, **params) -> dict | None:
        try:
            resp = self._http.get(f"{self.base}{path}", params=params or None, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            return None

    def health(self) -> dict | None:
        return self._get_json("/api/health")

    def telemetry(self, limit: int = 40) -> dict | None:
        return self._get_json("/api/telemetry", limit=limit)

    def stats(self, source_id: str) -> dict | None:
        return self._get_json(f"/api/sources/{source_id}/stats")

    def upload(self, name: str, data: bytes, content_type: str) -> dict:
        try:
            resp = self._http.post(
                f"{self.base}/api/sources", files={"file": (name, data, content_type)}, timeout=(5, 600)
            )
        except requests.RequestException as exc:
            raise ApiError(f"Could not reach the backend at {self.base}: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise ApiError(str(detail))
        return resp.json()

    def panic(self, note: str = "") -> dict:
        try:
            resp = self._http.post(f"{self.base}/api/panic", json={"note": note}, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ApiError(f"Panic request failed: {exc}") from exc

    def image_bytes(self, source_id: str) -> bytes:
        resp = self._http.get(f"{self.base}/api/sources/{source_id}/image", timeout=10)
        resp.raise_for_status()
        return resp.content

    def stream_url(self, source_id: str) -> str:
        return f"{self.public}/api/sources/{source_id}/stream"

    def image_url(self, source_id: str) -> str:
        return f"{self.public}/api/sources/{source_id}/image"

    def relay_frames(self, source_id: str, max_fps: int = 12) -> Iterator[bytes]:
        """Yield JPEG frames parsed from the MJPEG stream (used by the Streamlit relay mode)."""
        url = f"{self.base}/api/sources/{source_id}/stream"
        with self._http.get(url, params={"max_fps": max_fps}, stream=True, timeout=(5, 30)) as resp:
            resp.raise_for_status()
            buf = b""
            for chunk in resp.iter_content(chunk_size=65536):
                buf += chunk
                while True:
                    start = buf.find(b"\xff\xd8")
                    if start < 0:
                        buf = b""
                        break
                    end = buf.find(b"\xff\xd9", start + 2)
                    if end < 0:
                        buf = buf[start:]
                        break
                    yield buf[start : end + 2]
                    buf = buf[end + 2 :]
