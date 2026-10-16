"""Smart Vision SOC console.  Run from the project root:  streamlit run frontend/app.py"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import streamlit as st
import streamlit.components.v1 as components

from frontend import theme, widgets as w
from frontend.client import ApiError, SmartVisionClient

API_URL = os.getenv("SV_API_URL", "http://127.0.0.1:8000")            # Streamlit server -> API
PUBLIC_API_URL = os.getenv("SV_PUBLIC_API_URL", API_URL)               # browser -> API
OPERATOR = os.getenv("SV_OPERATOR_NAME", "Operator 01")
ROLE = os.getenv("SV_OPERATOR_ROLE", "Shift lead")
STATION = os.getenv("SV_STATION", "SOC station 01")
NAV = ["Live Monitor", "Incident Log", "System Status"]
ACCEPTED = ["mp4", "avi", "mov", "mkv", "webm", "m4v", "jpg", "jpeg", "png", "bmp", "webp"]

st.set_page_config(page_title="Smart Vision", layout="wide", initial_sidebar_state="expanded")
st.markdown(theme.CSS, unsafe_allow_html=True)


def embed(html: str, height: int) -> None:
    """Render trusted, self-built HTML in an iframe (st.iframe on current Streamlit, else the legacy API)."""
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


client = get_client()
ss = st.session_state
for key, default in {
    "source": None, "upload_key": None, "upload_error": None,
    "panic_armed": False, "panic_result": None,
}.items():
    ss.setdefault(key, default)

health = get_health()


# ------------------------------------------------------------------ polled panels
@st.fragment(run_every="1s")
def telemetry_fragment() -> None:
    st.markdown(w.telemetry_html(get_snapshot()), unsafe_allow_html=True)


@st.fragment(run_every="1s")
def alerts_fragment() -> None:
    st.markdown(w.alerts_html(get_snapshot()), unsafe_allow_html=True)


# ------------------------------------------------------------------ top bar and sidebar
embed(w.navbar_html(PUBLIC_API_URL, OPERATOR, ROLE), w.NAVBAR_HEIGHT)

with st.sidebar:
    st.markdown(w.profile_html(OPERATOR, ROLE, STATION), unsafe_allow_html=True)
    page = st.radio("Navigation", NAV, key="nav", label_visibility="collapsed")
    st.markdown(w.side_foot_html(health), unsafe_allow_html=True)


# ------------------------------------------------------------------ source panel
def source_panel() -> None:
    st.markdown(w.panel_title("upload", "Video source"), unsafe_allow_html=True)
    ready = bool(health and health["model_loaded"])
    uploaded = st.file_uploader(
        "Video or image", type=ACCEPTED, key="uploader", label_visibility="collapsed", disabled=not ready,
    )
    if uploaded is None:
        if ss.upload_key is not None:  # file removed from the uploader: stop the feed
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
                     f"<div>{'Backend offline.' if not health else 'Model not loaded.'} {reason or ''}</div>"),
            unsafe_allow_html=True,
        )
    if ss.upload_error:
        st.markdown(w.notice("error", "Could not use this file", f"<div>{w.escape(ss.upload_error)}</div>"),
                    unsafe_allow_html=True)
    elif ss.source:
        s = ss.source
        detail = f"{s['width']}&times;{s['height']}" + (f" &middot; {s['fps']:.0f} fps" if s["kind"] == "video" else " &middot; image")
        st.markdown(f"<div class='muted' style='font-size:.8rem;margin-top:.5rem'>{w.escape(s['name'])} &middot; {detail}</div>",
                    unsafe_allow_html=True)
    st.toggle(
        "Relay frames through Streamlit", key="relay",
        help="Use only if your browser cannot reach the API directly. Slower and less smooth than the default.",
    )


# ------------------------------------------------------------------ panic widget
def panic_panel() -> None:
    st.markdown(w.panel_title("radio", "Panic link"), unsafe_allow_html=True)
    st.markdown(w.panic_status_html(health), unsafe_allow_html=True)
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
    st.markdown(w.panic_result_html(ss.panic_result), unsafe_allow_html=True)


# ------------------------------------------------------------------ relay fallback
def render_relay(src: dict, tele_slot, alert_slot) -> None:
    """Fallback transport: pull the MJPEG stream server-side and paint frames into st.empty()."""
    if src["kind"] == "image":
        st.image(client.image_bytes(src["id"]))
        return
    hud, frame = st.empty(), st.empty()
    last_panels = 0.0
    try:
        for jpg in client.relay_frames(src["id"]):
            frame.image(jpg, output_format="JPEG")
            now = time.time()
            if now - last_panels > 1.0:  # panels refresh at 1 Hz, video at stream rate
                last_panels = now
                hud.markdown(w.relay_hud_html(client.stats(src["id"])), unsafe_allow_html=True)
                snap = client.telemetry()
                tele_slot.markdown(w.telemetry_html(snap), unsafe_allow_html=True)
                alert_slot.markdown(w.alerts_html(snap), unsafe_allow_html=True)
    except requests.RequestException as exc:
        st.markdown(w.notice("error", "Relay interrupted", f"<div>{w.escape(str(exc))}</div>"),
                    unsafe_allow_html=True)
    stats = client.stats(src["id"])
    if stats:
        hud.markdown(w.relay_hud_html(stats), unsafe_allow_html=True)


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
    tele_slot = alert_slot = None

    with tele_box:
        st.markdown(w.panel_title("activity", "Daily telemetry", time.strftime("%d %b %Y")), unsafe_allow_html=True)
        if relay:
            tele_slot = st.empty()
            tele_slot.markdown(w.telemetry_html(get_snapshot()), unsafe_allow_html=True)
        else:
            telemetry_fragment()
    with panic_box:
        panic_panel()
    with alert_box:
        st.markdown(w.panel_title("bell", "Live alerts"), unsafe_allow_html=True)
        if relay:
            alert_slot = st.empty()
            alert_slot.markdown(w.alerts_html(get_snapshot()), unsafe_allow_html=True)
        else:
            alerts_fragment()

    with main:
        if health is None:
            st.markdown(
                w.notice("error", "Backend unreachable",
                         f"<div>No response from <code>{w.escape(API_URL)}</code>. Start it from the project root with "
                         "<code>uvicorn backend.api:app --port 8000</code>.</div>"),
                unsafe_allow_html=True,
            )
        src = ss.source
        if relay and src:
            render_relay(src, tele_slot, alert_slot)
        else:
            html = w.stage_html(
                PUBLIC_API_URL, src,
                client.stream_url(src["id"]) if src else None,
                client.image_url(src["id"]) if src else None,
            )
            embed(html, w.STAGE_HEIGHT)


def page_incidents() -> None:
    st.markdown("<h2 class='page-title'>Incident log</h2>"
                "<p class='page-sub'>Confirmed threats and panic events since the backend started, newest first.</p>",
                unsafe_allow_html=True)

    @st.fragment(run_every="2s")
    def table() -> None:
        with st.container(border=True):
            st.markdown(w.incident_table_html(get_snapshot(300)), unsafe_allow_html=True)

    table()


def page_system() -> None:
    st.markdown("<h2 class='page-title'>System status</h2>"
                "<p class='page-sub'>Live configuration of the detection pipeline. Change values with SV_* environment variables and restart the backend.</p>",
                unsafe_allow_html=True)

    @st.fragment(run_every="3s")
    def status() -> None:
        with st.container(border=True):
            st.markdown(w.system_html(get_health(), API_URL), unsafe_allow_html=True)

    status()


{"Live Monitor": page_live, "Incident Log": page_incidents, "System Status": page_system}[page]()
