"""YOLO model wrapper. One shared, lock-protected model serves all streams."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import Settings

log = logging.getLogger("smartvision.detector")


@dataclass(frozen=True, slots=True)
class Detection:
    label: str
    confidence: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    is_threat: bool = True

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "box": [round(v, 1) for v in self.box],
            "is_threat": self.is_threat,
        }


class YoloDetector:
    mock = False

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._model = None
        self._lock = threading.Lock()
        self._half = False
        self.device = "cpu"
        self.error: str | None = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        path = Path(self._s.model_path)
        if not path.is_file():
            self.error = f"Model weights not found at {path.resolve()} (set SV_MODEL_PATH)"
            raise FileNotFoundError(self.error)
        from ultralytics import YOLO  # imported lazily: heavy, and optional for mock/tests
        import torch

        cuda = torch.cuda.is_available()
        self.device = self._s.device or ("0" if cuda else "cpu")
        self._half = cuda and self.device not in {"cpu", "mps"}
        model = YOLO(str(path))
        # Warm-up so the first live frame does not pay the initialisation cost.
        model.predict(
            np.zeros((self._s.imgsz, self._s.imgsz, 3), np.uint8),
            conf=self._s.conf, imgsz=self._s.imgsz, device=self.device,
            half=self._half, verbose=False,
        )
        self._model = model
        self.error = None
        log.info("Model loaded: %s on %s (conf=%.2f)", path, self.device, self._s.conf)

    def _is_threat(self, label: str) -> bool:
        classes = self._s.threat_classes
        return not classes or label.lower() in classes

    def predict(self, image_bgr: np.ndarray) -> list[Detection]:
        """Run inference on a preprocessed BGR image. Boxes are in the input image's coordinates."""
        if self._model is None:
            raise RuntimeError("Detector is not loaded")
        with self._lock:  # Ultralytics predictors are not thread-safe
            result = self._model.predict(
                image_bgr, conf=self._s.conf, imgsz=self._s.imgsz, device=self.device,
                half=self._half, max_det=50, verbose=False,
            )[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
        xyxy = boxes.xyxy.cpu().numpy()
        conf = boxes.conf.cpu().numpy()
        cls = boxes.cls.cpu().numpy().astype(int)
        names = result.names
        detections = []
        for box, score, k in zip(xyxy, conf, cls):
            label = str(names.get(int(k), k))
            detections.append(
                Detection(label, float(score), tuple(float(v) for v in box), self._is_threat(label))
            )
        return detections


class MockDetector:
    """Development-only stand-in that emits a periodic fake box. Enabled with SV_MOCK_DETECTOR=1.

    It exists so the UI and API can be exercised without weights. It detects nothing real, and the
    health endpoint reports `mock: true` so the UI can say so.
    """

    mock = True
    device = "mock"
    error: str | None = None
    ready = True

    def __init__(self, settings: Settings) -> None:
        self._n = 0

    def load(self) -> None:  # noqa: D401
        return None

    def predict(self, image_bgr: np.ndarray) -> list[Detection]:
        self._n += 1
        if (self._n % 90) >= 45:
            return []
        h, w = image_bgr.shape[:2]
        return [Detection("mock-weapon", 0.87, (w * 0.34, h * 0.30, w * 0.66, h * 0.70), True)]


def create_detector(settings: Settings) -> YoloDetector | MockDetector:
    return MockDetector(settings) if settings.mock_detector else YoloDetector(settings)
