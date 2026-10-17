"""FastAPI app. Run from the project root:  uvicorn backend.api:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import __version__
from .config import get_settings
from .detector import create_detector
from .stream import SourceInfo, SourceRegistry, analyze_image, stream_frames
from .telemetry import TelemetryStore

log = logging.getLogger("smartvision.api")

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    detector = create_detector(settings)
    try:
        await run_in_threadpool(detector.load)
    except Exception as exc:  # stay up so /api/health can explain what is wrong
        detector.error = detector.error or str(exc)
        log.error("Detector failed to load: %s", exc)
    app.state.settings = settings
    app.state.detector = detector
    app.state.telemetry = TelemetryStore(settings.alert_cooldown_s)
    app.state.sources = SourceRegistry()
    app.state.started = time.time()
    yield


app = FastAPI(title="Smart Vision API", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=list(get_settings().cors_origins),
    allow_methods=["*"], allow_headers=["*"],
)


def _source_or_404(request: Request, source_id: str) -> SourceInfo:
    source = request.app.state.sources.get(source_id)
    if source is None:
        raise HTTPException(404, "Unknown source")
    return source


def _probe_video(path: Path) -> tuple[int, int, float, int]:
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError("OpenCV could not open this video (unsupported codec?)")
        ok, frame = cap.read()
        if not ok:
            raise ValueError("The video contains no readable frames")
        h, w = frame.shape[:2]
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = fps if fps and 1 <= fps <= 240 else 25.0
        return w, h, float(fps), max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
    finally:
        cap.release()


@app.get("/api/health")
async def health(request: Request) -> dict:
    s, det = request.app.state.settings, request.app.state.detector
    return {
        "status": "ok" if det.ready else "degraded",
        "version": __version__,
        "model_loaded": det.ready,
        "model_path": s.model_path,
        "error": det.error,
        "mock": det.mock,
        "device": det.device,
        "conf": getattr(s, 'conf', 0.30),
        "imgsz": s.imgsz,
        "preprocess": {"clahe": s.clahe, "clahe_clip": s.clahe_clip, "denoise": s.denoise},
        "sources": request.app.state.sources.count(),
        "panic_webhook_configured": bool(s.panic_webhook_url),
        "uptime_s": round(time.time() - request.app.state.started, 1),
    }


@app.post("/api/sources", status_code=201)
async def upload_source(request: Request, file: UploadFile = File(...)) -> dict:
    s, det = request.app.state.settings, request.app.state.detector
    if not det.ready:
        raise HTTPException(503, det.error or "Model is not loaded")
    name = Path(file.filename or "upload").name
    ext = Path(name).suffix.lower()
    kind = "video" if ext in VIDEO_EXT else "image" if ext in IMAGE_EXT else None
    if kind is None:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Use video ({', '.join(sorted(VIDEO_EXT))}) or image.")

    source_id = uuid.uuid4().hex[:12]
    dest = s.upload_dir / f"{source_id}{ext}"
    limit, size = s.max_upload_mb << 20, 0
    try:
        with dest.open("wb") as fh:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File exceeds {s.max_upload_mb} MB limit")
                fh.write(chunk)

        if kind == "video":
            w, h, fps, frames = await run_in_threadpool(_probe_video, dest)
            source = SourceInfo(source_id, name, kind, dest, w, h, fps, frames)
        else:
            probe = cv2.imread(str(dest))
            if probe is None:
                raise ValueError("Could not decode image")
            source = SourceInfo(source_id, name, kind, dest, probe.shape[1], probe.shape[0], 0.0, 1)
            await run_in_threadpool(analyze_image, source, det, s, request.app.state.telemetry)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from exc

    request.app.state.sources.add(source, s.max_sources)
    return source.to_public()


@app.get("/api/sources/{source_id}")
async def get_source(request: Request, source_id: str) -> dict:
    return _source_or_404(request, source_id).to_public()


@app.delete("/api/sources/{source_id}", status_code=204)
async def delete_source(request: Request, source_id: str) -> Response:
    if not request.app.state.sources.remove(source_id):
        raise HTTPException(404, "Unknown source")
    return Response(status_code=204)


@app.get("/api/sources/{source_id}/stats")
async def source_stats(request: Request, source_id: str) -> dict:
    source = _source_or_404(request, source_id)
    return {**source.stats.to_dict(), "kind": source.kind, "name": source.name,
            "width": source.width, "height": source.height, "source_fps": source.fps}


@app.get("/api/sources/{source_id}/image")
async def source_image(request: Request, source_id: str) -> Response:
    source = _source_or_404(request, source_id)
    if source.annotated_jpeg is None:
        raise HTTPException(400, "Source is not an image")
    return Response(source.annotated_jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


async def _pump(request: Request, frames):
    """Run the blocking generator in a worker thread; stop promptly when the client leaves."""
    loop = asyncio.get_running_loop()
    try:
        while True:
            if await request.is_disconnected():
                break
            chunk = await loop.run_in_executor(None, next, frames, None)
            if chunk is None:
                break
            yield chunk
    finally:
        try:
            frames.close()
        except ValueError:  # generator still mid-frame in its thread; GC will close it
            pass


@app.get("/api/sources/{source_id}/stream")
async def stream(request: Request, source_id: str, max_fps: float | None = Query(None, ge=1, le=60)):
    source = _source_or_404(request, source_id)
    if source.kind != "video":
        raise HTTPException(400, "Only video sources can be streamed")
    frames = stream_frames(source, request.app.state.detector, request.app.state.settings,
                           request.app.state.telemetry, max_fps)
    return StreamingResponse(
        _pump(request, frames),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/telemetry")
async def telemetry(request: Request, limit: int = Query(40, ge=1, le=300)) -> dict:
    return request.app.state.telemetry.snapshot(limit)


@app.get("/api/incidents")
async def incidents(request: Request) -> list[dict]:
    directory = request.app.state.settings.incidents_dir
    items = []
    for path in directory.glob("*.jpg"):
        try:
            created_at = path.stat().st_mtime
        except OSError:
            log.warning("Incident frame disappeared while listing: %s", path)
            continue
        items.append({
            "filename": path.name,
            "created_at": created_at,
            "url": f"/api/incidents/{path.name}",
        })
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items


@app.get("/api/incidents/{filename}")
async def incident_image(request: Request, filename: str) -> FileResponse:
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".jpg":
        raise HTTPException(404, "Unknown incident frame")
    path = request.app.state.settings.incidents_dir / filename
    if not path.is_file():
        raise HTTPException(404, "Unknown incident frame")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


class PanicIn(BaseModel):
    note: str = Field("", max_length=280)


def _post_webhook(url: str, payload: dict) -> tuple[bool, str]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - URL is operator-configured
            return 200 <= resp.status < 300, f"HTTP {resp.status}"
    except Exception as exc:
        return False, str(exc)


@app.post("/api/panic")
async def panic(request: Request, body: PanicIn) -> dict:
    s, store = request.app.state.settings, request.app.state.telemetry
    if not s.panic_webhook_url:
        store.record_event("panic", "warning", "Panic alert raised; no outbound channel configured (logged locally only)")
        return {"delivered": False, "channel": "none",
                "detail": "No SV_PANIC_WEBHOOK_URL configured. The alert was logged locally only."}
    payload = {"event": "smart_vision_panic", "ts": time.time(), "note": body.note}
    ok, detail = await run_in_threadpool(_post_webhook, s.panic_webhook_url, payload)
    store.record_event("panic", "critical" if ok else "warning",
                       "Panic alert delivered to webhook" if ok else f"Panic alert FAILED to deliver: {detail}")
    return {"delivered": ok, "channel": "webhook", "detail": detail}


# ------------------------------------------------------------------
# الإعدادات الديناميكية (Dynamic Settings Endpoint)
# ------------------------------------------------------------------
class SettingsUpdate(BaseModel):
    conf: float
    iou: float

@app.post("/update_settings")
async def update_settings(request: Request, body: SettingsUpdate) -> dict:
    s = request.app.state.settings
    det = request.app.state.detector
    
    # تحديث إعدادات التطبيق
    s.conf = body.conf
    setattr(s, 'iou', body.iou)
    
    # تحديث إعدادات المودل مباشرة إذا كان يدعمها
    if hasattr(det, 'conf'):
        det.conf = body.conf
    if hasattr(det, 'iou'):
        det.iou = body.iou
        
    log.info(f"Model settings updated: conf={body.conf}, iou={body.iou}")
    return {"message": "Settings updated successfully", "conf": body.conf, "iou": body.iou}
