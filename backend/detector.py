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
        
        self.conf = settings.conf
        self.iou = getattr(settings, 'iou', 0.45)

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        path = Path(self._s.model_path)
        if not path.is_file():
            self.error = f"Model weights not found at {path.resolve()} (set SV_MODEL_PATH)"
            raise FileNotFoundError(self.error)
        from ultralytics import YOLO
        import torch

        cuda = torch.cuda.is_available()
        self.device = self._s.device or ("0" if cuda else "cpu")
        is_engine = path.suffix.lower() == ".engine"
        if is_engine and (not cuda or self.device in {"cpu", "mps"}):
            self.error = "TensorRT .engine models require a CUDA device"
            raise RuntimeError(self.error)
        
        self._half = not is_engine and cuda and self.device not in {"cpu", "mps"}
        model = YOLO(str(path))
        
        model.predict(
            np.zeros((self._s.imgsz, self._s.imgsz, 3), np.uint8),
            conf=self.conf, iou=self.iou, imgsz=self._s.imgsz, device=self.device,
            half=self._half, verbose=False,
        )
        self._model = model
        self.error = None
        log.info("Model loaded: %s on %s", path, self.device)

    def _is_threat(self, label: str) -> bool:
        classes = self._s.threat_classes
        return not classes or label.lower() in classes

    def predict(self, image_bgr: np.ndarray) -> list[Detection]:
        if self._model is None:
            raise RuntimeError("Detector is not loaded")
        
        with self._lock:
            result = self._model.predict(
                image_bgr, conf=self.conf, iou=self.iou, imgsz=self._s.imgsz, device=self.device,
                half=self._half, max_det=50, verbose=False,
            )[0]
            
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []
            
        xyxy = boxes.xyxy.cpu().numpy()
        scores = boxes.conf.cpu().numpy()
        cls = boxes.cls.cpu().numpy().astype(int)
        names = result.names
        detections = []
        
        for box, score, k in zip(xyxy, scores, cls):
            # 1. فلترة العرض: لا تعرض أي شيء أقل من قيمة السلايدر
            if float(score) < float(self.conf):
                continue
                
            label = str(names.get(int(k), k))
            
            # 2. فلترة الحفظ الإجبارية: يعتبر "تهديد حقيقي" (ويتم حفظ صورته) فقط إذا كانت النسبة 60% فما فوق
            is_real_threat = self._is_threat(label) and float(score) >= 0.60
            
            detections.append(
                Detection(label, float(score), tuple(float(v) for v in box), is_real_threat)
            )
            
        return detections


class MockDetector:
    mock = True
    device = "mock"
    error: str | None = None
    ready = True

    def __init__(self, settings: Settings) -> None:
        self._n = 0
        self.conf = settings.conf
        self.iou = getattr(settings, 'iou', 0.45)

    def load(self) -> None:
        return None

    def predict(self, image_bgr: np.ndarray) -> list[Detection]:
        self._n += 1
        if (self._n % 90) >= 45:
            return []
        h, w = image_bgr.shape[:2]
        return [Detection("mock-weapon", 0.87, (w * 0.34, h * 0.30, w * 0.66, h * 0.70), True)]


def create_detector(settings: Settings) -> YoloDetector | MockDetector:
    return MockDetector(settings) if settings.mock_detector else YoloDetector(settings)
