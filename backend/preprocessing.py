"""Frame preprocessing applied before YOLO inference.

Pipeline: ensure 3-channel BGR uint8 -> letterbox to NxN -> optional denoise -> CLAHE contrast.

Colour note: Ultralytics treats numpy arrays as BGR (OpenCV convention), so the model input stays
BGR. RGB is only needed for display libraries; use `bgr_to_rgb` for that.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class LetterboxMeta:
    """Geometry needed to map model-space boxes back to the source frame."""

    scale: float
    pad_x: int
    pad_y: int
    src_w: int
    src_h: int


def ensure_bgr_uint8(frame: np.ndarray) -> np.ndarray:
    """Normalise any decoded frame (gray, BGRA, float) to HxWx3 uint8 BGR."""
    if frame is None or frame.size == 0:
        raise ValueError("Empty frame")
    if frame.dtype != np.uint8:
        frame = np.clip(frame, 0, 255).astype(np.uint8)
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if frame.ndim == 3:
        channels = frame.shape[2]
        if channels == 1:
            return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        if channels == 4:
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        if channels == 3:
            return frame
    raise ValueError(f"Unsupported frame shape {frame.shape}")


def bgr_to_rgb(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


class Preprocessor:
    """Stateful per-stream preprocessor (CLAHE objects are not thread-safe, so do not share)."""

    def __init__(
        self,
        size: int = 640,
        *,
        clahe: bool = True,
        clahe_clip: float = 1.5,
        clahe_tile: int = 8,
        denoise: bool = False,
        pad_value: int = 114,
    ) -> None:
        self.size = size
        self.denoise = denoise
        self.pad_value = pad_value
        self._clahe = (
            cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(clahe_tile, clahe_tile))
            if clahe
            else None
        )

    def letterbox(self, bgr: np.ndarray) -> tuple[np.ndarray, LetterboxMeta]:
        """Resize keeping aspect ratio, pad to a square canvas (no distortion of weapon shapes)."""
        h, w = bgr.shape[:2]
        scale = min(self.size / w, self.size / h)
        new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        resized = cv2.resize(bgr, (new_w, new_h), interpolation=interp)
        pad_x, pad_y = (self.size - new_w) // 2, (self.size - new_h) // 2
        canvas = np.full((self.size, self.size, 3), self.pad_value, dtype=np.uint8)
        canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
        return canvas, LetterboxMeta(scale, pad_x, pad_y, w, h)

    def _equalize(self, bgr: np.ndarray) -> np.ndarray:
        """CLAHE on the lightness channel only, so colours are not shifted."""
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l_chan, a_chan, b_chan = cv2.split(lab)
        l_chan = self._clahe.apply(l_chan)
        return cv2.cvtColor(cv2.merge((l_chan, a_chan, b_chan)), cv2.COLOR_LAB2BGR)

    def __call__(self, frame: np.ndarray, *, is_rgb: bool = False) -> tuple[np.ndarray, LetterboxMeta]:
        bgr = ensure_bgr_uint8(frame)
        if is_rgb:
            bgr = cv2.cvtColor(bgr, cv2.COLOR_RGB2BGR)
        boxed, meta = self.letterbox(bgr)
        if self.denoise:
            boxed = cv2.bilateralFilter(boxed, d=5, sigmaColor=35, sigmaSpace=35)
        if self._clahe is not None:
            boxed = self._equalize(boxed)
        return boxed, meta


def boxes_to_source(xyxy: np.ndarray, meta: LetterboxMeta) -> np.ndarray:
    """Map Nx4 xyxy boxes from letterboxed model space back to source-frame pixels."""
    out = np.asarray(xyxy, dtype=np.float32).reshape(-1, 4).copy()
    out[:, [0, 2]] = (out[:, [0, 2]] - meta.pad_x) / meta.scale
    out[:, [1, 3]] = (out[:, [1, 3]] - meta.pad_y) / meta.scale
    out[:, [0, 2]] = out[:, [0, 2]].clip(0, meta.src_w)
    out[:, [1, 3]] = out[:, [1, 3]].clip(0, meta.src_h)
    return out
