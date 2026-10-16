# Smart Vision

Real-time weapon and armed-robbery detection with a FastAPI backend and a Streamlit SOC console.

```
smart-vision/
├── backend/
│   ├── config.py         env-driven settings (SV_*)
│   ├── preprocessing.py  letterbox 640x640, BGR/RGB handling, CLAHE, optional denoise, box mapping
│   ├── detector.py       YOLO wrapper (conf=0.30), thread-safe; opt-in mock detector for development
│   ├── telemetry.py      incident store: daily counter, last incident, alert feed, cooldown
│   ├── stream.py         frame processor, real-time MJPEG frame generator, incident frame saving
│   └── api.py            FastAPI app
├── frontend/
│   ├── app.py            Streamlit app (navbar, sidebar, stage, right panel, 3 pages)
│   ├── theme.py          design tokens + global CSS
│   ├── widgets.py        HTML builders (navbar and stage iframes, panels)
│   └── client.py         API client, MJPEG relay parser
├── tests/test_pipeline.py
├── .streamlit/config.toml
└── .env.example
```

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# place best.engine (preferred) or best.pt in the project root, or set SV_MODEL_PATH

uvicorn backend.api:app --host 0.0.0.0 --port 8000     # terminal 1
streamlit run frontend/app.py                          # terminal 2
```

No weights yet? `SV_MOCK_DETECTOR=1 uvicorn backend.api:app` runs the whole UI with simulated
detections. The navbar and System page label it clearly. Never use it operationally.

## How smooth playback works

1. By default, Streamlit reads the FastAPI `multipart/x-mixed-replace` feed server-side and paints
   decoded JPEG frames with `st.image`. This avoids browser CORS and tunnel reachability problems.
   Turn off relay mode only when the browser can reach the API directly for native MJPEG playback.
2. The backend paces frames to the video's own clock. If inference is slower than the video, stale
   frames are skipped instead of queued, so the feed stays real-time rather than drifting behind.
3. FPS, detection counts, and the flashing threat alarm are polled from `/stats` and shown in the
   Streamlit panel; direct-browser mode also renders the in-feed HUD.
4. Alerts and telemetry refresh once per second through `st.fragment(run_every="1s")`.

The relay paints frames at up to 12 FPS. Direct browser playback is available as an opt-out for
deployments where the browser can reach the API and native MJPEG playback is preferred.

## Incident evidence and TensorRT

Each newly confirmed threat alert saves its annotated frame as a timestamped JPEG under
`SV_INCIDENT_DIR` (default `incidents/`). The Incident Log page lists and displays the most recent
saved frames. Repeated alerts suppressed by the configured per-source/label cooldown do not create
duplicate evidence files.

Set `SV_MODEL_PATH` to a compatible Ultralytics `.engine` file to load a TensorRT model. The engine
must be built for the deployment GPU; its FP16/FP32 precision is embedded in the engine, so runtime
inference leaves the `half` option to TensorRT. `.engine` models require CUDA.

## Deployment notes

- `SV_PUBLIC_API_URL` must be the address the **browser** uses to reach the API. If Streamlit is served
  over HTTPS, the API must be HTTPS too, or the browser blocks the stream as mixed content.
- Restrict `SV_CORS_ORIGINS` to your Streamlit origin in production.
- There is no authentication. Put both services behind your SSO or reverse proxy before exposing them.
- The operator name in the navbar comes from `SV_OPERATOR_NAME`; it is not a login.

## Accuracy notes

- Preprocessing should match your training conditions. CLAHE is on by default at a light setting. If your
  model was trained on raw frames, compare with `SV_CLAHE=0` on your validation clips.
- By default every class the model predicts counts as a threat. Set `SV_THREAT_CLASSES=pistol,knife`
  to restrict this.
- A threat is only logged after `SV_CONFIRM_FRAMES` (default 3) detections, with a per-label cooldown, so
  single-frame false positives do not flood the feed. Tune both on real footage.
- The panic link posts to `SV_PANIC_WEBHOOK_URL` when set. Without it, the alert is logged locally only
  and the UI says so.

## Tests

```bash
pytest -q
```
