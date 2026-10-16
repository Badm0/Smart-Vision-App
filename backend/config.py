"""Runtime configuration. Every value can be overridden with an SV_* environment variable."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _names(name: str, default: str = "") -> frozenset[str]:
    raw = os.getenv(name, default)
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    # Model
    model_path: str
    conf: float
    imgsz: int
    device: str
    threat_classes: frozenset[str]
    mock_detector: bool
    # Preprocessing
    clahe: bool
    clahe_clip: float
    denoise: bool
    # Streaming
    output_max_side: int
    jpeg_quality: int
    max_stream_fps: float
    detect_every: int
    realtime_sync: bool
    loop_video: bool
    # Incidents
    confirm_frames: int
    alert_cooldown_s: float
    incidents_dir: Path
    # Uploads
    upload_dir: Path
    max_upload_mb: int
    max_sources: int
    # Integration
    panic_webhook_url: str
    cors_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    upload_dir = Path(os.getenv("SV_UPLOAD_DIR", "uploads")).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    incidents_dir = Path(os.getenv("SV_INCIDENT_DIR", "incidents")).resolve()
    incidents_dir.mkdir(parents=True, exist_ok=True)
    default_model = "best.engine" if Path("best.engine").is_file() else "best.pt"
    return Settings(
        model_path=os.getenv("SV_MODEL_PATH") or default_model,
        conf=float(os.getenv("SV_CONF", "0.30")),
        imgsz=int(os.getenv("SV_IMGSZ", "640")),
        device=os.getenv("SV_DEVICE", ""),  # "" = auto (CUDA if available, else CPU)
        # Empty set = every class the model predicts counts as a threat.
        threat_classes=_names("SV_THREAT_CLASSES"),
        mock_detector=_bool("SV_MOCK_DETECTOR", False),
        clahe=_bool("SV_CLAHE", True),
        clahe_clip=float(os.getenv("SV_CLAHE_CLIP", "1.5")),
        denoise=_bool("SV_DENOISE", False),
        output_max_side=int(os.getenv("SV_OUTPUT_MAX_SIDE", "960")),
        jpeg_quality=int(os.getenv("SV_JPEG_QUALITY", "80")),
        max_stream_fps=float(os.getenv("SV_MAX_STREAM_FPS", "30")),
        detect_every=max(1, int(os.getenv("SV_DETECT_EVERY", "1"))),
        realtime_sync=_bool("SV_REALTIME_SYNC", True),
        loop_video=_bool("SV_LOOP_VIDEO", True),
        confirm_frames=max(1, int(os.getenv("SV_CONFIRM_FRAMES", "3"))),
        alert_cooldown_s=float(os.getenv("SV_ALERT_COOLDOWN_S", "6")),
        incidents_dir=incidents_dir,
        upload_dir=upload_dir,
        max_upload_mb=int(os.getenv("SV_MAX_UPLOAD_MB", "500")),
        max_sources=max(1, int(os.getenv("SV_MAX_SOURCES", "8"))),
        panic_webhook_url=os.getenv("SV_PANIC_WEBHOOK_URL", "").strip(),
        cors_origins=tuple(
            o.strip() for o in os.getenv("SV_CORS_ORIGINS", "*").split(",") if o.strip()
        ),
    )
