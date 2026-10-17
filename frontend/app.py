from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import requests
import streamlit as st
import streamlit.components.v1 as components

from frontend import theme, widgets as w
from frontend.client import ApiError, SmartVisionClient

API_URL = (os.getenv("SV_API_URL") or "http://127.0.0.1:8000").strip().rstrip("/")
PUBLIC_API_URL = (os.getenv("SV_PUBLIC_API_URL") or API_URL).strip().rstrip("/")
OPERATOR = os.getenv("SV_OPERATOR_NAME", "Operator 01")
ROLE = os.getenv("SV_OPERATOR_ROLE", "Shift lead")
STATION = os.getenv("SV_STATION", "SOC station 01")
NAV = ["Live Monitor", "Incident Log", "System Status"]
ACCEPTED = ["mp4", "avi", "mov", "mkv", "webm", "m4v", "jpg", "jpeg", "png", "bmp", "webp"]

st.set_page_config(page_title="Smart Vision", layout="wide", initial_sidebar_state="expanded")

# 🛑 الحل الجذري لمشكلة ظهور الـ CSS كنص: تغليف الكود إجبارياً وإزالة المسافات الوهمية
safe_css = theme.CSS.strip() if "<style>" in theme.CSS else f"<style>\n{theme.CSS.strip()}\n</style>"
st.markdown(safe_css, unsafe_allow_html=True)


def embed(html: str, height: int) -> None:
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        components.html(html, height=height)


@st.cache_resource
def get_client() -> SmartVisionClient:
    return SmartVisionClient(API_URL, PUBLIC_API_URL)


@st.cache_data(ttl=2, show_spinner=False)
def get_health() -> dict | None:
    return get_client().health()


@st.cache_data(ttl=0.8, show_spinner=False)
def get_snapshot(limit: int = 40) -> dict | None:
    return get_client().telemetry(limit)


@st.cache_data(ttl=2, show_spinner=False)
def get_incidents() -> list[dict] | None:
    return get_client().incidents()


client = get_client()
ss = st.session_state
for key, default in {
    "source": None, "upload_key": None, "upload_error": None,
    "panic_armed": False, "panic_result": None, "relay": True,
}.items():
    ss.setdefault(key, default)

health = get_health()


# ------------------------------------------------------------------ polled panels
@st.fragment(run_every="1s")
def telemetry_fragment(source_id: str | None = None) -> None:
    st.markdown(w.telemetry_html(get_snapshot()).strip(), unsafe_allow_html=True)
    if source_id:
        st.markdown(w.live_status_html(client.stats(source_id)).strip(), unsafe_allow_html=True)


@st.fragment(run_every="1s")
def alerts_fragment() -> None:
    st.markdown(w.alerts_html(get_snapshot()).strip(), unsafe_allow_html=True)


@st.fragment(run_every="3s")
def navbar_fragment() -> None:
    embed(w.navbar_html(OPERATOR, ROLE, get_health()), w.NAVBAR_HEIGHT)


# ------------------------------------------------------------------ top bar and sidebar
navbar_fragment()

with st.sidebar:
    # 🛑 استخدام strip() هنا لمنع ظهور كود الـ HTML كنص في القائمة الجانبية
    st.markdown(w.profile_html(OPERATOR, ROLE, STATION).strip(), unsafe_allow_html=True)
    page = st.radio("Navigation", NAV, key="nav", label_visibility="collapsed")
    st.markdown(w.side_foot_html(health).strip(), unsafe_allow_html=True)
    
    st.markdown("<hr style='margin: 1rem 0; border-color: #333;'>", unsafe_allow_html=True)
    st.markdown("<div style='color: #888; font-size: 0.8rem; margin-bottom: 0.5rem;'>⚙️ MODEL SETTINGS</div>", unsafe_allow_html=True)
    
    new_conf = st.slider("Confidence", 0.1, 1.0, 0.30, 0.05)
    new_iou = st.slider("IoU Threshold", 0.1, 1.0, 0.45, 0.05)
    
    if st.button("Apply Parameters", use_container_width=True):
        try:
            requests.post(f"{API_URL}/update_settings", json={"conf": new_conf, "iou": new_iou})
            st.success("Applied!")
        except Exception as e:
            st.error("Backend not ready.")


# ------------------------------------------------------------------ source panel
def source_panel() -> None:
    st.markdown(w.panel_title("upload", "Video source").strip(), unsafe_allow_html=True)
    ready = bool(health and health["model_loaded"])
    uploaded = st.file_uploader(
        "Video or image", type=ACCEPTED, key="uploader", label_visibility="collapsed", disabled=not ready,
    )
    if uploaded is None:
        if ss.upload_key is not None:
            ss.source, ss.upload_key, ss.upload_error = None, None, None
    else:
        file_key = getattr(uploaded, "file_id", None) or f"{uploaded.name}:{uploaded.size}"
        if file_key != ss.upload_key:
            ss.upload_key = file_key
            try:
                with st.spinner("Uploading and validating"):
                    ss.source = client.upload(
                        uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream"
                    )
                ss.upload_error = None
            except ApiError as exc:
                ss.source, ss.upload_error = None, str(exc)

    if not ready:
        reason = (health or {}).get("error") if health else None
        st.markdown(
            w.notice("warn", "Uploads disabled",
                     f"<div>{'Backend offline.' if not health else 'Model not loaded.'} {reason or ''}</div>").strip(),
            unsafe_allow_html=True,
        )
    if ss.upload_error:
        st.markdown(w.notice("error", "Could not use this file", f"<div>{w.escape(ss.upload_error)}</div>").strip(),
                    unsafe_allow_html=True)
    elif ss.source:
        s = ss.source
        detail = f"{s['width']}&times;{s['height']}" + (f" &middot; {s['fps']:.0f} fps" if s["kind"] == "video" else " &middot; image")
        st.markdown(f"<div class='muted' style='font-size:.8rem;margin-top:.5rem'>{w.escape(s['name'])} &middot; {detail}</div>",
                    unsafe_allow_html=True)
    st.toggle(
        "Relay frames through Streamlit", key="relay",
        help="Recommended: Streamlit fetches and displays frames, avoiding browser CORS and tunnel issues. Turn off only when the browser can reach the API directly.",
    )


# ------------------------------------------------------------------ panic widget
def panic_panel() -> None:
    st.markdown(w.panel_title("radio", "Panic link").strip(), unsafe_allow_html=True)
    st.markdown(w.panic_status_html(health).strip(), unsafe_allow_html=True)
    if ss.panic_armed:
        configured = bool(health and health["panic_webhook_configured"])
        copy = ("This sends an alert to the configured channel." if configured
                else "No channel is configured. This will only be logged locally.")
        st.markdown(f"<p class='confirm-copy'>{copy}</p>", unsafe_allow_html=True)
        if st.button("Confirm and send", key="panic_confirm"):
            try:
                ss.panic_result = client.panic(f"Triggered by {OPERATOR} at {STATION}")
            except ApiError as exc:
                ss.panic_result = {"delivered": False, "detail": str(exc)}
            ss.panic_armed = False
            st.rerun()
        if st.button("Cancel", key="panic_cancel"):
            ss.panic_armed = False
            st.rerun()
    else:
        if st.button("Trigger panic alert", key="panic_arm", disabled=health is None):
            ss.panic_armed, ss.panic_result = True, None
            st.rerun()
    st.markdown(w.panic_result_html(ss.panic_result).strip(), unsafe_allow_html=True)


# ------------------------------------------------------------------ Relay Video Logic (Base64 + OpenCV)
def close_relay_stream() -> None:
    pass

def render_relay(source: dict) -> None:
    if source["kind"] == "image":
        st.image(client.image_bytes(source["id"]), use_container_width=True)
    else:
        video_placeholder = st.empty()
        stream_url = client.stream_url(source["id"])
        
        try:
            cap = cv2.VideoCapture(stream_url)
            while cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    b64 = base64.b64encode(buffer).decode("utf-8")
                    video_placeholder.markdown(
                        f"<img src='data:image/jpeg;base64,{b64}' style='width: 100%; border-radius: 8px;'>",
                        unsafe_allow_html=True
                    )
                    time.sleep(0.03)
                else:
                    st.info("Video stream ended.")
                    break
            cap.release()
        except Exception as exc:
            st.warning(f"Relay interrupted: {exc}")


# ------------------------------------------------------------------ Live Incidents Fragment
@st.fragment(run_every="2s")
def live_incidents_fragment() -> None:
    images = get_incidents()
    if not images:
        st.info("لا توجد أسلحة مكتشفة حتى الآن.")
        return
        
    recent_images = images[:4]
    cols = st.columns(4)
    for col, item in zip(cols, recent_images):
        with col:
            try:
                img_source = client.incident_image(item["filename"])
                if isinstance(img_source, str):
                    local_url = img_source.replace(PUBLIC_API_URL, API_URL)
                    res = requests.get(local_url, timeout=5)
                    if res.status_code == 200:
                        st.image(res.content, use_container_width=True)
                else:
                    st.image(img_source, use_container_width=True)
                
                time_str = time.strftime("%H:%M:%S", time.gmtime(item["created_at"]))
                st.caption(f"⏱️ {time_str}")
            except Exception:
                pass


# ------------------------------------------------------------------ pages
def page_live() -> None:
    main, side = st.columns([2.7, 1], gap="medium")
    with side:
        src_box = st.container(border=True)
        tele_box = st.container(border=True)
        panic_box = st.container(border=True)
        alert_box = st.container(border=True)

    with src_box:
        source_panel()
    relay = bool(ss.get("relay"))
    if not relay or not ss.source or ss.source["kind"] != "video":
        close_relay_stream()

    with tele_box:
        st.markdown(w.panel_title("activity", "Daily telemetry", time.strftime("%d %b %Y")).strip(), unsafe_allow_html=True)
        telemetry_fragment(ss.source["id"] if ss.source else None)
    with panic_box:
        panic_panel()
    with alert_box:
        st.markdown(w.panel_title("bell", "Live alerts").strip(), unsafe_allow_html=True)
        alerts_fragment()

    with main:
        if health is None:
            st.markdown(
                w.notice("error", "Backend unreachable",
                         f"<div>No response from <code>{w.escape(API_URL)}</code>. Start it from the project root with "
                         "<code>uvicorn backend.api:app --port 8000</code>.</div>").strip(),
                unsafe_allow_html=True,
            )
        
        src = ss.source
        video_container = st.container()
        incidents_container = st.container()
        
        if src:
            with incidents_container:
                st.markdown("<hr style='border-color: #333; margin: 1rem 0;'>", unsafe_allow_html=True)
                st.markdown("<h4 style='color: #ff4b4b;'>🔴 التهديدات المباشرة (لقطات الأسلحة)</h4>", unsafe_allow_html=True)
                live_incidents_fragment()

        with video_container:
            if relay and src:
                render_relay(src)
            elif not relay and src:
                html = w.stage_html(
                    PUBLIC_API_URL, src,
                    client.stream_url(src["id"]) if src else None,
                    client.image_url(src["id"]) if src else None,
                )
                embed(html, w.STAGE_HEIGHT)


def page_incidents() -> None:
    st.markdown("<h2 class='page-title'>Incident log</h2>"
                "<p class='page-sub'>Confirmed threats and panic events, newest first.</p>",
                unsafe_allow_html=True)

    @st.fragment(run_every="2s")
    def table() -> None:
        with st.container(border=True):
            st.markdown(w.incident_table_html(get_snapshot(300)).strip(), unsafe_allow_html=True)
        st.markdown(w.panel_title("alert", "Saved incident frames").strip(), unsafe_allow_html=True)
        images = get_incidents()
        if images is None:
            st.markdown(w.notice("warn", "Frames unavailable", "<div>The backend did not respond.</div>").strip(),
                        unsafe_allow_html=True)
        elif not images:
            st.markdown("<div class='empty'><b>No saved frames</b>Annotated frames are saved when a threat alert is confirmed.</div>",
                        unsafe_allow_html=True)
        else:
            for start in range(0, min(len(images), 12), 3):
                columns = st.columns(3)
                for column, item in zip(columns, images[start:start + 3]):
                    with column:
                        try:
                            img_source = client.incident_image(item["filename"])
                            if isinstance(img_source, str):
                                local_url = img_source.replace(PUBLIC_API_URL, API_URL)
                                res = requests.get(local_url, timeout=5)
                                if res.status_code == 200:
                                    st.image(res.content, use_container_width=True)
                                else:
                                    st.error("صورة غير متاحة")
                            else:
                                st.image(img_source, use_container_width=True)
                                
                            caption = time.strftime(
                                "%Y-%m-%d %H:%M:%S UTC", time.gmtime(item["created_at"])
                            )
                            st.caption(f"{item['filename']} · {caption}")
                        except Exception:
                            st.warning("خطأ في الاتصال")

    table()


def page_system() -> None:
    st.markdown("<h2 class='page-title'>System status</h2>"
                "<p class='page-sub'>Live configuration of the detection pipeline. Change values with SV_* environment variables and restart the backend.</p>",
                unsafe_allow_html=True)

    @st.fragment(run_every="3s")
    def status() -> None:
        with st.container(border=True):
            st.markdown(w.system_html(get_health(), API_URL).strip(), unsafe_allow_html=True)

    status()


{"Live Monitor": page_live, "Incident Log": page_incidents, "System Status": page_system}[page]()
