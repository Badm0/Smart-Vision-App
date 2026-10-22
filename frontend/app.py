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

from frontend import widgets as w
from frontend.client import ApiError, SmartVisionClient

API_URL = (os.getenv("SV_API_URL") or "http://127.0.0.1:8000").strip().rstrip("/")
PUBLIC_API_URL = (os.getenv("SV_PUBLIC_API_URL") or API_URL).strip().rstrip("/")
OPERATOR = os.getenv("SV_OPERATOR_NAME", "Operator 01")
ROLE = os.getenv("SV_OPERATOR_ROLE", "Shift lead")
STATION = os.getenv("SV_STATION", "SOC station 01")
NAV = ["Live Monitor", "Incident Log", "System Status"]
ACCEPTED = ["mp4", "avi", "mov", "mkv", "webm", "m4v", "jpg", "jpeg", "png", "bmp", "webp"]

st.set_page_config(page_title="Smart Vision Hub", layout="wide", initial_sidebar_state="expanded")


# ------------------------------------------------------------------ Custom Animated Design
def inject_navy_animated_design():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Inter:wght@400;500;600;700&display=swap');

    /* Keep Streamlit's native sidebar and its built-in open/close controls available. */
    [data-testid="stSidebar"] {
        position: relative;
        z-index: 100 !important;
        background: rgba(8, 14, 30, 0.94) !important;
        border-right: 1px solid rgba(56, 189, 248, 0.28) !important;
        box-shadow: 10px 0 35px rgba(0, 0, 0, 0.28) !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        background: rgba(8, 14, 30, 0.90) !important;
        backdrop-filter: blur(20px) !important;
        -webkit-backdrop-filter: blur(20px) !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 1rem !important;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p {
        color: #e2e8f0;
    }

    /* The native header contains Streamlit's sidebar toggle, so never hide it. */
    [data-testid="stHeader"] {
        background: rgba(4, 7, 17, 0.30) !important;
        z-index: 1000 !important;
    }
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"] {
        opacity: 1 !important;
    }
    [data-testid="stHeader"] button,
    [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button,
    [data-testid="stSidebarCollapsedControl"] button {
        color: #38BDF8 !important;
        background: rgba(15, 23, 42, 0.82) !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        border-radius: 10px !important;
    }

    /* Keep the menu/toolbar available; only hide Streamlit's unrelated footer/menu. */
    #MainMenu, footer {
        visibility: hidden !important;
    }

    html, body, .stApp, [data-testid="stAppViewContainer"], .main {
        background: transparent !important;
        background-color: transparent !important;
        font-family: 'Inter', sans-serif !important;
        color: #e2e8f0 !important;
    }

    .block-container {
        max-width: 96% !important;
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        position: relative;
        z-index: 10 !important;
    }

    /* البطاقات الزجاجية الداكنة */
    [data-testid="stVerticalBlockBorderWrapper"], div[data-testid="stForm"] {
        background: rgba(15, 23, 42, 0.72) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(56, 189, 248, 0.28) !important;
        border-radius: 24px !important;
        box-shadow: 0 15px 35px rgba(0, 0, 0, 0.35), 0 0 20px rgba(56, 189, 248, 0.06) !important;
        padding: 20px !important;
        margin-bottom: 18px !important;
    }

    /* الهيدر العلوي */
    .hub-header-card {
        background: rgba(15, 23, 42, 0.78);
        backdrop-filter: blur(16px);
        border-radius: 22px;
        padding: 18px 28px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        border: 1px solid rgba(56, 189, 248, 0.3);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        margin-bottom: 20px;
    }
    .hub-brand {
        display: flex;
        align-items: center;
        gap: 15px;
    }
    .hub-logo-box {
        width: 50px;
        height: 50px;
        background: rgba(6, 11, 25, 0.9);
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 2px solid #38BDF8;
        box-shadow: 0 0 15px rgba(56, 189, 248, 0.25);
    }
    .hub-title {
        font-family: 'Orbitron', sans-serif !important;
        color: #2EE59D !important;
        font-size: 1.45rem !important;
        font-weight: 800 !important;
        letter-spacing: 2px;
        margin: 0 !important;
        text-shadow: 0 0 15px rgba(46, 229, 157, 0.35);
    }
    .hub-credit-badge {
        display: inline-block;
        padding: 6px 20px;
        border: 1.5px solid #2EE59D;
        border-radius: 10px;
        color: #2EE59D !important;
        font-weight: 600;
        font-size: 0.8rem;
        letter-spacing: 1.5px;
        background: rgba(46, 229, 157, 0.08);
    }

    /* الأزرار العامة */
    .stButton > button {
        width: 100% !important;
        background: rgba(15, 23, 42, 0.8) !important;
        color: #38BDF8 !important;
        border: 1.5px solid rgba(56, 189, 248, 0.45) !important;
        border-radius: 14px !important;
        padding: 10px 18px !important;
        font-weight: 600 !important;
        letter-spacing: 1px !important;
        transition: all 0.25s ease !important;
    }
    .stButton > button:hover {
        background: #38BDF8 !important;
        color: #060b19 !important;
        box-shadow: 0 0 20px rgba(56, 189, 248, 0.4) !important;
        transform: translateY(-1px) !important;
    }
    .stButton > button p, .stButton > button span {
        color: inherit !important;
        font-weight: 600 !important;
    }

    /* حقول الإدخال */
    .stTextInput input {
        border-radius: 999px !important;
        border: 1.5px solid rgba(56, 189, 248, 0.5) !important;
        background-color: rgba(6, 11, 25, 0.75) !important;
        color: #f8fafc !important;
        padding: 10px 20px !important;
    }

    /* صندوق رفع الملفات */
    [data-testid="stFileUploaderDropzone"] {
        background: rgba(6, 11, 25, 0.65) !important;
        border: 1.5px dashed #38BDF8 !important;
        border-radius: 16px !important;
        color: #cbd5e1 !important;
    }

    /* شريط عنوان الكاميرا وزر Full Screen */
    .cam-topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(56, 189, 248, 0.18);
    }
    .cam-title {
        color: #38BDF8 !important;
        font-weight: 700;
        font-size: 0.95rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 72%;
    }
    .fs-btn {
        background: rgba(56, 189, 248, 0.12);
        color: #2EE59D !important;
        border: 1.5px solid #2EE59D;
        border-radius: 10px;
        padding: 5px 14px;
        font-size: 0.8rem;
        font-weight: 700;
        cursor: pointer;
        transition: all 0.2s ease;
        letter-spacing: 0.5px;
    }
    .fs-btn:hover {
        background: #2EE59D;
        color: #060b19 !important;
        box-shadow: 0 0 15px rgba(46, 229, 157, 0.45);
    }

    .video-card-wrapper {
        text-align: center;
        position: relative;
    }
    .stream-frame {
        border-radius: 16px;
        border: 2px solid rgba(56, 189, 248, 0.45);
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.45);
    }
    </style>
    """, unsafe_allow_html=True)

    # 2. Inject the animated navy background and fullscreen overlay
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            
            // Keep the real Streamlit sidebar in place. Do not clone it into a modal:
            // cloned Streamlit widgets lose their framework event handlers.

            // أ. خلفية النيلي المتحركة
            let canvas = doc.getElementById('cbi-network-canvas');
            if (!canvas) {
                canvas = doc.createElement('canvas');
                canvas.id = 'cbi-network-canvas';
                canvas.style.position = 'fixed';
                canvas.style.top = '0';
                canvas.style.left = '0';
                canvas.style.width = '100vw';
                canvas.style.height = '100vh';
                canvas.style.zIndex = '0';
                canvas.style.pointerEvents = 'none';
                doc.body.prepend(canvas);

                const ctx = canvas.getContext('2d');
                let width, height, particles;

                function resize() {
                    width = canvas.width = window.parent.innerWidth;
                    height = canvas.height = window.parent.innerHeight;
                }
                window.parent.addEventListener('resize', resize);
                resize();

                particles = [];
                const count = 75;
                for (let i = 0; i < count; i++) {
                    particles.push({
                        x: Math.random() * width,
                        y: Math.random() * height,
                        vx: (Math.random() - 0.5) * 1.1,
                        vy: (Math.random() - 0.5) * 1.1,
                        r: Math.random() * 2.5 + 1.5,
                        color: Math.random() > 0.3 ? '#38BDF8' : '#2EE59D'
                    });
                }

                let mouse = { x: null, y: null };
                window.parent.addEventListener('mousemove', (e) => {
                    mouse.x = e.clientX;
                    mouse.y = e.clientY;
                });

                function animate() {
                    ctx.clearRect(0, 0, width, height);
                    for (let i = 0; i < particles.length; i++) {
                        let p = particles[i];
                        p.x += p.vx;
                        p.y += p.vy;
                        if (p.x < 0 || p.x > width) p.vx *= -1;
                        if (p.y < 0 || p.y > height) p.vy *= -1;

                        ctx.beginPath();
                        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                        ctx.fillStyle = p.color;
                        ctx.fill();

                        for (let j = i + 1; j < particles.length; j++) {
                            let p2 = particles[j];
                            let dx = p.x - p2.x;
                            let dy = p.y - p2.y;
                            let dist = Math.sqrt(dx * dx + dy * dy);
                            if (dist < 165) {
                                ctx.beginPath();
                                ctx.moveTo(p.x, p.y);
                                ctx.lineTo(p2.x, p2.y);
                                ctx.strokeStyle = `rgba(56, 189, 248, ${0.45 * (1 - dist / 165)})`;
                                ctx.lineWidth = 1.2;
                                ctx.stroke();
                            }
                        }

                        if (mouse.x && mouse.y) {
                            let dx = p.x - mouse.x;
                            let dy = p.y - mouse.y;
                            let dist = Math.sqrt(dx * dx + dy * dy);
                            if (dist < 180) {
                                ctx.beginPath();
                                ctx.moveTo(p.x, p.y);
                                ctx.lineTo(mouse.x, mouse.y);
                                ctx.strokeStyle = `rgba(46, 229, 157, ${0.55 * (1 - dist / 180)})`;
                                ctx.lineWidth = 1.4;
                                ctx.stroke();
                            }
                        }
                    }
                    requestAnimationFrame(animate);
                }
                animate();
            }
            canvas.style.background = 'radial-gradient(circle at 50% 20%, #101f42 0%, #070d1f 65%, #040711 100%)';

            // ج. نافذة Full Screen
            let overlay = doc.getElementById('sv-fs-overlay');
            if (!overlay) {
                overlay = doc.createElement('div');
                overlay.id = 'sv-fs-overlay';
                overlay.style.cssText = 'display:none; position:fixed; inset:0; background:rgba(4,7,17,0.96); z-index:999999; flex-direction:column; align-items:center; justify-content:center; backdrop-filter:blur(12px);';
                overlay.innerHTML = `
                    <div style="position:absolute; top:22px; right:32px; z-index:1000000;">
                        <button id="sv-fs-close" style="background:#ef4444; color:#fff; border:none; padding:10px 22px; border-radius:12px; font-weight:700; cursor:pointer; font-size:0.95rem; box-shadow:0 5px 15px rgba(239,68,68,0.4);">✕ Exit Full Screen (ESC)</button>
                    </div>
                    <img id="sv-fs-img" style="max-width:94vw; max-height:88vh; border-radius:18px; border:2px solid #2EE59D; box-shadow:0 0 40px rgba(46,229,157,0.25); object-fit:contain;" />
                `;
                doc.body.appendChild(overlay);

                const closeFs = () => {
                    window.parent.activeFsCam = null;
                    overlay.style.display = 'none';
                    if (doc.fullscreenElement) doc.exitFullscreen().catch(() => {});
                };

                overlay.querySelector('#sv-fs-close').addEventListener('click', closeFs);
                overlay.addEventListener('click', (e) => { if (e.target === overlay) closeFs(); });
                doc.addEventListener('keydown', (e) => { if (e.key === 'Escape' && window.parent.activeFsCam) closeFs(); });

                doc.addEventListener('click', (e) => {
                    const btn = e.target.closest('.fs-btn');
                    if (btn) {
                        window.parent.activeFsCam = btn.getAttribute('data-cam-id');
                        overlay.style.display = 'flex';
                        if (overlay.requestFullscreen) overlay.requestFullscreen().catch(() => {});
                    }
                });

                setInterval(() => {
                    const camId = window.parent.activeFsCam;
                    if (camId) {
                        const srcImg = doc.querySelector(`img.stream-frame[data-cam-id="${camId}"]`);
                        const fsImg = doc.getElementById('sv-fs-img');
                        if (srcImg && fsImg && srcImg.src) fsImg.src = srcImg.src;
                    }
                }, 30);
            }
        })();
        </script>
        """,
        height=0, width=0
    )

inject_navy_animated_design()


# ------------------------------------------------------------------ Clients & State
@st.cache_resource
def get_client() -> SmartVisionClient:
    return SmartVisionClient(API_URL, PUBLIC_API_URL)

@st.cache_data(ttl=2, show_spinner=False)
def get_health() -> dict | None:
    return get_client().health()

@st.cache_data(ttl=2, show_spinner=False)
def get_incidents() -> list[dict] | None:
    return get_client().incidents()

client = get_client()
ss = st.session_state
for key, default in {
    "logged_in": False,
    "active_sources": [],
    "saved_sources": {},
    "frame_scale": 100,
    "relay": True,
}.items():
    ss.setdefault(key, default)

health = get_health()


# ------------------------------------------------------------------ Header Banner
def render_hub_header(badge_text: str):
    st.markdown(f"""
    <div class="hub-header-card">
        <div class="hub-brand">
            <div class="hub-logo-box">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                    <circle cx="12" cy="11" r="3" stroke="#2EE59D"></circle>
                </svg>
            </div>
            <div>
                <div class="hub-title">SMART VISION HUB</div>
                <div style="font-size:0.78rem; color:#94a3b8;">AI Threat & Weapon Detection Center</div>
            </div>
        </div>
        <div class="hub-credit-badge">{badge_text}</div>
    </div>
    """, unsafe_allow_html=True)


# ------------------------------------------------------------------ Login Screen
def login_page():
    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        render_hub_header("LOCKED")
        with st.form("login_form"):
            st.markdown("<h4 style='text-align:center; color:#38BDF8 !important; margin-bottom:15px;'>🔒 Operator Login</h4>", unsafe_allow_html=True)
            username = st.text_input("Username", placeholder="Username (admin)", label_visibility="collapsed")
            password = st.text_input("Password", type="password", placeholder="Password (admin)", label_visibility="collapsed")
            submit = st.form_submit_button("ACCESS HUB", use_container_width=True)
            
            if submit:
                if username == "admin" and password == "admin":
                    ss.logged_in = True
                    st.rerun()
                else:
                    st.error("Invalid username or password!")

if not ss.logged_in:
    login_page()
    st.stop()


# ------------------------------------------------------------------ Left Sidebar Content
with st.sidebar:
    st.markdown(w.profile_html(OPERATOR, ROLE, STATION).strip(), unsafe_allow_html=True)
    page = st.radio("Navigation", NAV, key="nav", label_visibility="collapsed")
    
    st.markdown("<hr style='margin: 1rem 0; border-color: rgba(56, 189, 248, 0.2);'>", unsafe_allow_html=True)
    st.markdown("<div style='color: #38BDF8; font-weight: 700; font-size: 0.85rem; margin-bottom: 0.5rem; letter-spacing:1px;'>🎥 VIDEO SOURCES</div>", unsafe_allow_html=True)
    
    ready = bool(health and health.get("model_loaded"))
    uploaded_files = st.file_uploader(
        "Upload multiple videos", type=ACCEPTED, accept_multiple_files=True, disabled=not ready, label_visibility="collapsed"
    )
    
    current_names = [f.name for f in uploaded_files] if uploaded_files else []
    for name in list(ss.saved_sources.keys()):
        if name not in current_names:
            del ss.saved_sources[name]
            
    if uploaded_files:
        for f in uploaded_files:
            if f.name not in ss.saved_sources:
                try:
                    with st.spinner(f"Uploading {f.name}..."):
                        src = client.upload(f.name, f.getvalue(), f.type or "application/octet-stream")
                        ss.saved_sources[f.name] = src
                except ApiError as exc:
                    st.error(f"Error with {f.name}: {exc}")
    
    if ss.saved_sources:
        selected_vids = st.multiselect(
            "Select Active Streams:",
            list(ss.saved_sources.keys()),
            default=list(ss.saved_sources.keys())
        )
        ss.active_sources = [ss.saved_sources[v] for v in selected_vids]
    else:
        ss.active_sources = []

    st.markdown("<hr style='margin: 1rem 0; border-color: rgba(56, 189, 248, 0.2);'>", unsafe_allow_html=True)
    st.markdown("<div style='color: #2EE59D; font-weight: 700; font-size: 0.85rem; margin-bottom: 0.5rem; letter-spacing:1px;'>📐 FRAME & SIZE CONTROL</div>", unsafe_allow_html=True)
    
    ss.frame_scale = st.slider("Frame Width (%)", min_value=50, max_value=100, value=100, step=5)
    grid_cols_choice = st.radio("Layout Mode:", ["2 Columns Grid", "1 Column (Large)"], horizontal=True)
    
    st.markdown("<hr style='margin: 1rem 0; border-color: rgba(56, 189, 248, 0.2);'>", unsafe_allow_html=True)
    if st.button("Logout", use_container_width=True):
        ss.logged_in = False
        st.rerun()


# ------------------------------------------------------------------ Top Header
status_badge = "ONLINE · MODEL READY" if (health and health.get("model_loaded")) else "BACKEND OFFLINE"
render_hub_header(status_badge)


# ------------------------------------------------------------------ Multi-Screen Video Streamer
def render_multiple_relays(sources: list[dict]):
    num_sources = len(sources)
    if num_sources == 0:
        return

    cam_options = ["🔍 All Cameras (Grid)"] + [f"📺 {s['name']}" for s in sources]
    selected_focus = st.pills("Camera Focus:", cam_options, default=cam_options[0], label_visibility="collapsed") if hasattr(st, "pills") else st.radio("Select View:", cam_options, horizontal=True, label_visibility="collapsed")

    if selected_focus and selected_focus != "🔍 All Cameras (Grid)":
        target_name = selected_focus.replace("📺 ", "")
        sources = [s for s in sources if s["name"] == target_name]
        num_sources = len(sources)

    placeholders = []
    caps = []
    
    num_cols = 1 if (num_sources == 1 or grid_cols_choice == "1 Column (Large)") else 2
    
    for i in range(0, num_sources, num_cols):
        cols = st.columns(num_cols, gap="medium")
        for j in range(num_cols):
            if i + j < num_sources:
                source = sources[i + j]
                with cols[j]:
                    with st.container(border=True):
                        st.markdown(
                            f"""
                            <div class="cam-topbar">
                                <div class="cam-title">🎥 {w.escape(source['name'])}</div>
                                <button type="button" class="fs-btn" data-cam-id="{source['id']}">⛶ Full Screen</button>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                        if source["kind"] == "image":
                            st.image(client.image_bytes(source["id"]), use_container_width=True)
                            placeholders.append(None)
                            caps.append(None)
                        else:
                            placeholders.append((st.empty(), source["id"]))
                            caps.append(cv2.VideoCapture(client.stream_url(source["id"])))

    try:
        while True:
            active = False
            for i, cap in enumerate(caps):
                if cap is not None and cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        active = True
                        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        b64 = base64.b64encode(buffer).decode("utf-8")
                        ph, cam_id = placeholders[i]
                        
                        ph.markdown(
                            f"""
                            <div class="video-card-wrapper">
                                <img src="data:image/jpeg;base64,{b64}" 
                                     class="stream-frame" 
                                     data-cam-id="{cam_id}"
                                     style="width: {ss.frame_scale}%; height: auto; object-fit: contain;">
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    else:
                        ph, _ = placeholders[i]
                        ph.info("Video stream ended.")
                        cap.release()
            if not active:
                break
            time.sleep(0.03)
    except Exception as exc:
        st.warning(f"Stream interrupted: {exc}")
    finally:
        for cap in caps:
            if cap is not None:
                cap.release()



def page_live():
    if health is None:
        st.warning("⚠️ Backend is offline. Please make sure FastAPI is running on port 8000.")
    
    if not ss.active_sources:
        with st.container(border=True):
            st.markdown(
                "<div style='text-align:center; padding: 50px 20px; color:#94a3b8 !important; font-size:1.05rem;'>"
                "👈 Use Streamlit’s native sidebar toggle in the top-left corner to open the control panel, upload and select your test videos."
                "</div>",
                unsafe_allow_html=True
            )
    else:
        render_multiple_relays(ss.active_sources)



def page_incidents():
    with st.container(border=True):
        search_inc = st.text_input("Search incidents", placeholder="Search saved weapon detections...", label_visibility="collapsed")
        st.markdown("<h4 style='color:#2EE59D !important; margin-top:10px;'>🔴 Confirmed Threat Captures (Confidence ≥ 60%)</h4>", unsafe_allow_html=True)
        
        images = get_incidents()
        if images is None:
            st.warning("Backend offline: Could not fetch incident frames.")
        elif not images:
            st.markdown("<div style='text-align:center; padding:30px; color:#94a3b8 !important;'>No weapon threats recorded yet.</div>", unsafe_allow_html=True)
        else:
            filtered = [item for item in images if search_inc.lower() in item["filename"].lower()]
            for start in range(0, min(len(filtered), 12), 3):
                cols = st.columns(3)
                for col, item in zip(cols, filtered[start:start + 3]):
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
                            caption = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(item["created_at"]))
                            st.caption(f"📁 {item['filename']} · ⏱️ {caption}")
                        except Exception:
                            st.warning("Connection error")


# ------------------------------------------------------------------ Page 3: SYSTEM STATUS
def page_system():
    with st.container(border=True):
        st.markdown("<h4 style='color:#38BDF8 !important;'>⚙️ System Telemetry & Emergency</h4>", unsafe_allow_html=True)
        if health:
            c1, c2, c3 = st.columns(3)
            c1.metric("Status", health.get("status", "ok").upper())
            c2.metric("Device", str(health.get("device", "CPU")))
            c3.metric("Confidence", f"{int(health.get('conf', 0.3)*100)}%")
        else:
            st.warning("Backend unreachable.")
            
        st.markdown("<hr style='border-color: rgba(56,189,248,0.2);'>", unsafe_allow_html=True)
        if st.button("🚨 TRIGGER PANIC ALERT", use_container_width=True, disabled=health is None):
            try:
                client.panic(f"Triggered by {OPERATOR} at {STATION}")
                st.success("Panic alert dispatched!")
            except ApiError as exc:
                st.error(f"Failed: {exc}")


{"Live Monitor": page_live, "Incident Log": page_incidents, "System Status": page_system}[page]()
