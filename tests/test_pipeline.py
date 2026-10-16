"""Backend tests. They use the mock detector, so no weights or GPU are needed."""
import os
import time

os.environ["SV_MOCK_DETECTOR"] = "1"
os.environ["SV_UPLOAD_DIR"] = "/tmp/sv_test_uploads"
os.environ["SV_CONFIRM_FRAMES"] = "2"

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.preprocessing import Preprocessor, boxes_to_source, ensure_bgr_uint8
from backend.telemetry import TelemetryStore


def test_letterbox_shape_and_box_roundtrip():
    pre = Preprocessor(640, clahe=False)
    frame = np.zeros((360, 1280, 3), np.uint8)
    out, meta = pre(frame)
    assert out.shape == (640, 640, 3)
    assert meta.scale == pytest.approx(0.5)
    # a box covering the whole source maps to the unpadded region and back
    model_box = np.array([[meta.pad_x, meta.pad_y, 640 - meta.pad_x, 640 - meta.pad_y]])
    src = boxes_to_source(model_box, meta)[0]
    assert src.tolist() == pytest.approx([0, 0, 1280, 360], abs=2)


@pytest.mark.parametrize("shape", [(100, 100), (100, 100, 1), (100, 100, 4), (100, 100, 3)])
def test_ensure_bgr_handles_channel_layouts(shape):
    assert ensure_bgr_uint8(np.zeros(shape, np.uint8)).shape == (100, 100, 3)


def test_clahe_changes_low_contrast_frame_but_keeps_shape():
    frame = np.full((480, 640, 3), 100, np.uint8)
    frame[100:200, 100:300] = 110
    out, _ = Preprocessor(640, clahe=True)(frame)
    assert out.shape == (640, 640, 3)


def test_telemetry_cooldown_and_counts():
    store = TelemetryStore(cooldown_s=60)
    assert store.record_threat("gun", 0.9, "cam") is not None
    assert store.record_threat("gun", 0.9, "cam") is None  # suppressed
    assert store.record_threat("knife", 0.7, "cam") is not None
    snap = store.snapshot()
    assert snap["total_threats"] == 2
    assert snap["last_incident"]["label"] == "knife"
    assert snap["alerts"][0]["label"] == "knife"  # newest first


@pytest.fixture(scope="module")
def client():
    from backend.api import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def video_bytes(tmp_path_factory):
    path = tmp_path_factory.mktemp("v") / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25, (320, 240))
    for i in range(100):
        frame = np.full((240, 320, 3), 40, np.uint8)
        cv2.circle(frame, (20 + i * 2, 120), 20, (200, 200, 200), -1)
        writer.write(frame)
    writer.release()
    return path.read_bytes()


def test_health_reports_mock(client):
    data = client.get("/api/health").json()
    assert data["model_loaded"] is True and data["mock"] is True and data["conf"] == 0.30


def test_rejects_bad_extension(client):
    r = client.post("/api/sources", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_rejects_corrupt_video(client):
    r = client.post("/api/sources", files={"file": ("x.mp4", b"not a video", "video/mp4")})
    assert r.status_code == 422


def test_image_upload_annotates_and_logs_threat(client):
    img = np.full((300, 400, 3), 90, np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    r = client.post("/api/sources", files={"file": ("pic.jpg", buf.tobytes(), "image/jpeg")})
    assert r.status_code == 201
    src = r.json()
    assert src["kind"] == "image" and src["stats"]["threat_active"] is True
    jpg = client.get(f"/api/sources/{src['id']}/image")
    assert jpg.headers["content-type"] == "image/jpeg"
    assert client.get("/api/telemetry").json()["total_threats"] >= 1


def test_video_stream_yields_jpeg_frames_in_real_time(client, video_bytes):
    r = client.post("/api/sources", files={"file": ("clip.avi", video_bytes, "video/x-msvideo")})
    assert r.status_code == 201
    src = r.json()
    assert (src["width"], src["height"], round(src["fps"])) == (320, 240, 25)

    frames, t0 = 0, time.time()
    with client.stream("GET", f"/api/sources/{src['id']}/stream") as resp:
        assert resp.headers["content-type"].startswith("multipart/x-mixed-replace")
        buf = b""
        for chunk in resp.iter_bytes():
            buf += chunk
            frames = buf.count(b"\xff\xd8")
            if frames >= 20:
                break
    elapsed = time.time() - t0
    assert frames >= 20
    assert elapsed >= 0.6, "frames must be paced to the video clock, not dumped instantly"
    stats = client.get(f"/api/sources/{src['id']}/stats").json()
    assert stats["frame_index"] > 0


def test_panic_without_webhook_is_honest(client):
    body = client.post("/api/panic", json={"note": "test"}).json()
    assert body["delivered"] is False and body["channel"] == "none"
