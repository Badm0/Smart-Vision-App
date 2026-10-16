"""Thin HTTP client for the Smart Vision backend."""
from __future__ import annotations

from typing import Any, Iterator

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

    def _get_json(self, path: str, **params) -> Any | None:
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

    def incidents(self) -> list[dict] | None:
        return self._get_json("/api/incidents")

    def incident_image(self, filename: str) -> bytes:
        try:
            resp = self._http.get(f"{self.base}/api/incidents/{filename}", timeout=self.timeout)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            raise ApiError(f"Could not load incident frame {filename}: {exc}") from exc

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
        """Yield JPEG payloads from multipart MJPEG without relying on browser access to the API."""
        url = f"{self.base}/api/sources/{source_id}/stream"
        with self._http.get(url, params={"max_fps": max_fps}, stream=True, timeout=(5, 30)) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            boundary = next(
                (part.split("=", 1)[1].strip().strip('"')
                 for part in content_type.split(";") if part.strip().lower().startswith("boundary=")),
                "",
            )
            if not boundary:
                raise ApiError("Backend stream did not provide a multipart boundary")
            marker = f"--{boundary}".encode("ascii")
            buf = bytearray()
            for chunk in resp.iter_content(chunk_size=65536):
                buf.extend(chunk)
                while True:
                    start = buf.find(marker)
                    if start < 0:
                        if len(buf) > len(marker):
                            del buf[:-len(marker)]
                        break
                    header_end = buf.find(b"\r\n\r\n", start + len(marker))
                    if header_end < 0:
                        if start:
                            del buf[:start]
                        break
                    header = bytes(buf[start + len(marker):header_end]).lower()
                    content_length = next(
                        (int(line.split(b":", 1)[1].strip()) for line in header.split(b"\r\n")
                         if line.startswith(b"content-length:")),
                        None,
                    )
                    if content_length is None or content_length < 0 or content_length > 32 << 20:
                        raise ApiError("Backend stream frame is missing a valid Content-Length")
                    payload_start = header_end + 4
                    payload_end = payload_start + content_length
                    if len(buf) < payload_end + 2:
                        if start:
                            del buf[:start]
                        break
                    yield bytes(buf[payload_start:payload_end])
                    del buf[:payload_end]
