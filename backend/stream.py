"""Sources, per-frame processing and the real-time frame generator."""
from __future__ import annotations

import logging
import requests
import re
import threading
import time
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

from .config import Settings
from .detector import Detection
from .preprocessing import Preprocessor, boxes_to_source
from .telemetry import TelemetryStore

log = logging.getLogger("smartvision.stream")

RED = (68, 68, 239)    # #EF4444 (BGR)
CYAN = (248, 189, 56)  # #38BDF8 (BGR)
INK = (22, 11, 7)      # #070B16 (BGR)
FONT = cv2.FONT_HERSHEY_SIMPLEX


@dataclass(slots=True)
class StreamStats:
    state: str = "idle"  # idle | live | still | ended
    fps: float = 0.0
    infer_ms: float = 0.0
    frame_index: int = 0
    threat_active: bool = False
    detections: list = field(default_factory=list)
    clients: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SourceInfo:
    id: str
    name: str
    kind: str  # "video" | "image"
    path: Path
    width: int
    height: int
    fps: float
    frame_count: int
    created_at: float = field(default_factory=time.time)
    stats: StreamStats = field(default_factory=StreamStats)
    annotated_jpeg: bytes | None = None

    def to_public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "kind": self.kind, "width": self.width,
            "height": self.height, "fps": self.fps, "frame_count": self.frame_count,
            "created_at": self.created_at, "stats": self.stats.to_dict(),
        }


class SourceRegistry:
    def __init__(self) -> None:
        self._items: dict[str, SourceInfo] = {}
        self._lock = threading.Lock()

    def add(self, source: SourceInfo, max_items: int) -> None:
        with self._lock:
            self._items[source.id] = source
            while len(self._items) > max_items:
                oldest = min(self._items.values(), key=lambda s: s.created_at)
                self._drop(oldest.id)

    def get(self, source_id: str) -> SourceInfo | None:
        with self._lock:
            return self._items.get(source_id)

    def remove(self, source_id: str) -> bool:
        with self._lock:
            return self._drop(source_id)

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def _drop(self, source_id: str) -> bool:
        source = self._items.pop(source_id, None)
        if source is None:
            return False
        try:
            source.path.unlink(missing_ok=True)
        except OSError:  # e.g. file still open on Windows
            log.warning("Could not delete %s", source.path)
        return True


@dataclass(slots=True)
class FrameResult:
    image: np.ndarray
    detections: list[Detection]
    ran_inference: bool
    infer_ms: float


def draw_detections(img: np.ndarray, detections: list[Detection], scale: float) -> None:
    for det in detections:
        x1, y1, x2, y2 = (int(round(v * scale)) for v in det.box)
        color = RED if det.is_threat else CYAN
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
        text = f"{det.label.upper()} {det.confidence * 100:.0f}%"
        (tw, th), base = cv2.getTextSize(text, FONT, 0.5, 1)
        top = max(0, y1 - th - base - 6)
        cv2.rectangle(img, (x1, top), (x1 + tw + 10, top + th + base + 6), color, -1)
        cv2.putText(img, text, (x1 + 5, top + th + 2), FONT, 0.5, INK, 1, cv2.LINE_AA)


class FrameProcessor:
    """Preprocess -> detect -> annotate, with threat confirmation across frames."""

    def __init__(self, detector, settings: Settings, telemetry: TelemetryStore, source: SourceInfo) -> None:
        self.detector, self.s, self.telemetry, self.source = detector, settings, telemetry, source
        self.pre = Preprocessor(
            settings.imgsz, clahe=settings.clahe, clahe_clip=settings.clahe_clip,
            denoise=settings.denoise,
        )
        self._last: list[Detection] = []
        self._tick = 0
        self._streak = 0

    def _display_frame(self, frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        longest = max(h, w)
        if longest <= self.s.output_max_side:
            return frame
        k = self.s.output_max_side / longest
        return cv2.resize(frame, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)

    def process(self, frame: np.ndarray, *, force_detect: bool = False) -> FrameResult:
        ran = force_detect or (self._tick % self.s.detect_every == 0)
        self._tick += 1
        infer_ms = 0.0
        if ran:
            t0 = time.perf_counter()
            model_in, meta = self.pre(frame)
            raw = self.detector.predict(model_in)
            if raw:
                boxes = boxes_to_source(np.array([d.box for d in raw]), meta)
                raw = [replace(d, box=tuple(float(v) for v in b)) for d, b in zip(raw, boxes)]
            self._last = raw
            infer_ms = (time.perf_counter() - t0) * 1000
        out = self._display_frame(frame)
        draw_detections(out, self._last, out.shape[1] / frame.shape[1])
        return FrameResult(out, self._last, ran, infer_ms)

    def register(self, result: FrameResult) -> None:
        """Confirm a threat only after it persists, so one-frame flickers do not raise alerts."""
        if not result.ran_inference:
            return
        threats = [d for d in result.detections if d.is_threat]
        if threats:
            self._streak += 1
            if self._streak >= self.s.confirm_frames:
                best = max(threats, key=lambda d: d.confidence)
                alert = self.telemetry.record_threat(best.label, best.confidence, self.source.name)
                if alert:
                    save_incident_frame(result.image, best, self.source, self.s, self.telemetry)
        else:
            self._streak = max(0, self._streak - 1)


def send_telegram_alert(image_path: str, label: str, conf: float, source_name: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    caption = f"🚨 إنذار أمني (Smart Vision)!\n\n🔍 التهديد: {label.upper()}\n🎯 الدقة: {conf*100:.0f}%\n🎥 الكاميرا: {source_name}"
    
    try:
        with open(image_path, 'rb') as photo:
            requests.post(url, data={'chat_id': chat_id, 'caption': caption}, files={'photo': photo}, timeout=10)
    except Exception as e:
        log.error(f"Telegram alert failed: {e}")


def save_incident_frame(
    image: np.ndarray, detection: Detection, source: SourceInfo,
    settings: Settings, telemetry: TelemetryStore,
) -> str | None:
    """Persist an annotated frame for each newly accepted threat alert."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    source_token = re.sub(r"[^A-Za-z0-9-]+", "-", Path(source.name).stem).strip("-")[:32] or "source"
    label_token = re.sub(r"[^A-Za-z0-9-]+", "-", detection.label).strip("-")[:32] or "threat"
    filename = f"{timestamp}_{source_token}_{label_token}.jpg"
    path = settings.incidents_dir / filename
    try:
        ok = cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not ok:
            raise OSError(f"OpenCV could not encode incident frame {path}")
    except (OSError, cv2.error) as exc:
        log.exception("Could not save incident frame for %s", source.name)
        telemetry.record_event("system", "warning", f"Incident frame could not be saved: {exc}", source.name)
        return None
        
    log.info("Saved incident frame: %s", path)
    
    # إرسال التنبيه للتليجرام بخيط منفصل (Thread)
    threading.Thread(
        target=send_telegram_alert, 
        args=(str(path), detection.label, detection.confidence, source.name),
        daemon=True
    ).start()
    
    return filename


def analyze_image(source: SourceInfo, detector, settings: Settings, telemetry: TelemetryStore) -> list[Detection]:
    frame = cv2.imread(str(source.path))
    if frame is None:
        raise ValueError("Could not decode image")
    processor = FrameProcessor(detector, settings, telemetry, source)
    result = processor.process(frame, force_detect=True)
    ok, buf = cv2.imencode(".jpg", result.image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise ValueError("Could not encode annotated image")
    source.annotated_jpeg = buf.tobytes()
    threats = [d for d in result.detections if d.is_threat]
    if threats:  # a still image is one observation: log it immediately
        best = max(threats, key=lambda d: d.confidence)
        alert = telemetry.record_threat(best.label, best.confidence, source.name)
        if alert:
            save_incident_frame(result.image, best, source, settings, telemetry)
    stats = source.stats
    stats.state = "still"
    stats.threat_active = bool(threats)
    stats.detections = [d.to_dict() for d in result.detections]
    stats.infer_ms = result.infer_ms
    return result.detections


def _part(jpeg: bytes) -> bytes:
    return (
        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
        + str(len(jpeg)).encode()
        + b"\r\n\r\n" + jpeg + b"\r\n"
    )


def stream_frames(
    source: SourceInfo, detector, settings: Settings, telemetry: TelemetryStore,
    max_fps: float | None = None,
) -> Iterator[bytes]:
    """Yield multipart JPEG parts paced to the video's real clock.

    If inference is slower than the video, stale frames are skipped (grab without decode/infer)
    so playback stays in real time instead of drifting behind like a laggy feed.
    """
    cap = cv2.VideoCapture(str(source.path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {source.name}")
    processor = FrameProcessor(detector, settings, telemetry, source)
    stats = source.stats
    src_fps = source.fps or 25.0
    min_interval = 1.0 / max(1.0, min(max_fps or settings.max_stream_fps, settings.max_stream_fps))
    encode = [int(cv2.IMWRITE_JPEG_QUALITY), settings.jpeg_quality]

    stats.state, stats.clients = "live", stats.clients + 1
    start, idx, empty_reads, last_t = time.perf_counter(), 0, 0, 0.0
    try:
        while True:
            now = time.perf_counter()
            if settings.realtime_sync:
                target = int((now - start) * src_fps)
                if target - idx > src_fps * 2:  # long stall: resync the clock, do not fast-forward
                    start, target = now - idx / src_fps, idx
                while idx < target:
                    if not cap.grab():
                        break
                    idx += 1
            ok, frame = cap.read()
            if not ok:
                if settings.loop_video and empty_reads < 2:
                    empty_reads += 1
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    idx, start = 0, time.perf_counter()
                    continue
                break
            empty_reads = 0
            idx += 1

            result = processor.process(frame)
            processor.register(result)
            ok, buf = cv2.imencode(".jpg", result.image, encode)
            if not ok:
                continue

            t_yield = time.perf_counter()
            if last_t:
                inst = 1.0 / max(t_yield - last_t, 1e-6)
                stats.fps = inst if stats.fps == 0 else 0.9 * stats.fps + 0.1 * inst
            last_t = t_yield
            stats.frame_index = idx
            if result.ran_inference:
                stats.infer_ms = 0.8 * stats.infer_ms + 0.2 * result.infer_ms
                stats.detections = [d.to_dict() for d in result.detections]
                stats.threat_active = any(d.is_threat for d in result.detections)
            yield _part(buf.tobytes())

            deadline = max(start + idx / src_fps, t_yield + min_interval)
            delay = deadline - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
    finally:
        cap.release()
        stats.clients = max(0, stats.clients - 1)
        if stats.clients == 0:
            stats.state, stats.threat_active, stats.fps = "ended", False, 0.0
