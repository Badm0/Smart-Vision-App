"""HTML builders for the SOC console.

Markup returned for st.markdown is deliberately single-line (no blank lines or 4-space indents),
because Markdown would otherwise turn it into code blocks.
"""
from __future__ import annotations

import json
import time
from html import escape

from .theme import FONT_LINK, TOKENS

STAGE_HEIGHT = 580
NAVBAR_HEIGHT = 64

_ICONS = {
    "logo": "<path d='M12 2 4 5v6c0 5 3.4 9.3 8 11 4.6-1.7 8-6 8-11V5z'/><circle cx='12' cy='11' r='3'/>",
    "alert": "<path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'/><path d='M12 9v4M12 17h.01'/>",
    "info": "<circle cx='12' cy='12' r='9'/><path d='M12 16v-4M12 8h.01'/>",
    "upload": "<path d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'/><path d='m17 8-5-5-5 5M12 3v12'/>",
    "activity": "<path d='M22 12h-4l-3 9L9 3l-3 9H2'/>",
    "radio": "<circle cx='12' cy='12' r='2'/><path d='M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19.1 4.9a10 10 0 0 1 0 14.2M4.9 19.1a10 10 0 0 1 0-14.2'/>",
    "bell": "<path d='M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9'/><path d='M13.7 21a2 2 0 0 1-3.4 0'/>",
    "camera-off": "<path d='m2 2 20 20'/><path d='M7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h14M9.5 4h5L17 7h3a2 2 0 0 1 2 2v7.5'/><path d='M14.5 14.5a3 3 0 0 1-4-4'/>",
}


def _js(value) -> str:
    """JSON for embedding inside <script>: neutralises '</script>' in user-controlled values."""
    return json.dumps(value).replace("</", "<\\/")


def icon(name: str, size: int = 16) -> str:
    return (
        f"<svg width='{size}' height='{size}' viewBox='0 0 24 24' fill='none' stroke='currentColor' "
        f"stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{_ICONS[name]}</svg>"
    )


def _hms(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


def _ago(ts: float, now: float) -> str:
    d = max(0, int(now - ts))
    if d < 60:
        return f"{d}s ago"
    if d < 3600:
        return f"{d // 60}m ago"
    return f"{d // 3600}h ago"


def panel_title(icon_name: str, text: str, aside: str = "") -> str:
    aside_html = f"<span class='aside'>{escape(aside)}</span>" if aside else ""
    return f"<h3 class='panel-title'>{icon(icon_name)}{escape(text)}{aside_html}</h3>"


def notice(kind: str, title: str, body_html: str) -> str:
    return f"<div class='notice {kind}'><b>{escape(title)}</b>{body_html}</div>"


def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


# ---------------------------------------------------------------- sidebar
def profile_html(name: str, role: str, station: str) -> str:
    return (
        f"<div class='profile'><div class='avatar'>{escape(initials(name))}</div>"
        f"<div><b>{escape(name)}</b><span>{escape(role)}</span><span>{escape(station)}</span></div></div>"
    )


def side_foot_html(health: dict | None) -> str:
    if not health:
        return "<div class='side-foot'>Backend offline</div>"
    return (
        f"<div class='side-foot'>Detection threshold <span class='data'>{health['conf']:.2f}</span><br>"
        f"Model input <span class='data'>{health['imgsz']}&times;{health['imgsz']}</span><br>"
        f"Device <span class='data'>{escape(str(health['device']))}</span></div>"
    )


# ---------------------------------------------------------------- right panel
def telemetry_html(snap: dict | None) -> str:
    if snap is None:
        return notice("warn", "Telemetry unavailable", "<div>The backend did not respond.</div>")
    last = snap["last_incident"]
    if last:
        last_html = (
            f"<span class='data'>{_hms(last['ts'])}</span> "
            f"<span class='muted'>{escape(str(last['label']).title())} {last['confidence'] * 100:.0f}%</span>"
        )
    else:
        last_html = "<span class='muted'>No incidents today</span>"
    total_cls = "big data crit" if snap["total_threats"] else "big data"
    return (
        f"<dl class='kv'><div><dt>Total threats today</dt><dd class='{total_cls}'>{snap['total_threats']}</dd></div>"
        f"<div><dt>Last incident</dt><dd>{last_html}</dd></div></dl>"
    )


def live_status_html(stats: dict | None) -> str:
    if not stats:
        return ""
    fps = float(stats.get("fps", 0.0))
    active = bool(stats.get("threat_active"))
    alert = (
        "<div class='alarm active' role='alert'>THREAT DETECTED</div>"
        if active else "<div class='alarm'>NO ACTIVE THREAT</div>"
    )
    detections = len(stats.get("detections", []))
    return (
        f"<div class='live-metrics'>{alert}<span class='chip'>{fps:.1f} FPS</span>"
        f"<span class='chip'>DETECTIONS {detections}</span></div>"
    )


def alerts_html(snap: dict | None, limit: int = 12) -> str:
    if snap is None:
        return notice("warn", "Alerts unavailable", "<div>The backend did not respond.</div>")
    alerts = snap["alerts"][:limit]
    if not alerts:
        return (
            "<div class='empty'><b>No alerts yet</b>A detection that persists across several frames "
            "is logged here with its source and time.</div>"
        )
    now = snap.get("server_time", time.time())
    icon_for = {"critical": "alert", "warning": "alert", "info": "info"}
    rows = []
    for a in alerts:
        sev = a["severity"] if a["severity"] in icon_for else "info"
        src = f" &middot; {escape(a['source'])}" if a.get("source") else ""
        rows.append(
            f"<li class='alert {sev}'>{icon(icon_for[sev], 18)}"
            f"<div><p class='a-msg'>{escape(a['message'])}</p><p class='a-meta'><span class='data'>{_hms(a['ts'])}</span>{src}</p></div>"
            f"<span class='a-ago'>{_ago(a['ts'], now)}</span></li>"
        )
    return f"<ul class='alerts'>{''.join(rows)}</ul>"


def panic_status_html(health: dict | None) -> str:
    if not health:
        dot, text = "bad", "Backend offline: panic link cannot send"
    elif health["panic_webhook_configured"]:
        dot, text = "ok", "Link armed: webhook channel configured"
    else:
        dot, text = "warn", "No channel configured: alerts are logged locally only"
    return f"<div class='link-row'><span class='dot {dot}'></span><span>{text}</span></div>"


def panic_result_html(result: dict | None) -> str:
    if not result:
        return ""
    if result.get("delivered"):
        return notice("ok", "Panic alert delivered", f"<div>{escape(str(result.get('detail', '')))}</div>")
    return notice("warn", "Not delivered", f"<div>{escape(str(result.get('detail', '')))}</div>")


# ---------------------------------------------------------------- pages 2 and 3
def incident_table_html(snap: dict | None) -> str:
    if snap is None:
        return notice("warn", "Incident log unavailable", "<div>The backend did not respond.</div>")
    if not snap["alerts"]:
        return "<div class='empty'><b>The log is empty</b>Confirmed threats and panic events appear here.</div>"
    rows = "".join(
        f"<tr><td class='data'>{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(a['ts']))}</td>"
        f"<td><span class='pill {a['severity']}'>{escape(a['severity'])}</span></td>"
        f"<td>{escape(a['message'])}</td><td class='muted'>{escape(a.get('source') or '-')}</td></tr>"
        for a in snap["alerts"]
    )
    return (
        "<table class='tbl'><thead><tr><th>Time</th><th>Severity</th><th>Event</th><th>Source</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def system_html(health: dict | None, api_url: str) -> str:
    if not health:
        return notice(
            "error", "Backend unreachable",
            f"<div>No response from <code>{escape(api_url)}</code>. Start it with "
            "<code>uvicorn backend.api:app --port 8000</code>.</div>",
        )
    pre = health["preprocess"]
    rows = [
        ("Status", health["status"]), ("Model", health["model_path"]), ("Device", health["device"]),
        ("Confidence threshold", f"{health['conf']:.2f}"), ("Model input", f"{health['imgsz']}x{health['imgsz']}"),
        ("CLAHE contrast", f"on (clip {pre['clahe_clip']})" if pre["clahe"] else "off"),
        ("Denoise", "on" if pre["denoise"] else "off"), ("Active sources", health["sources"]),
        ("Uptime", f"{health['uptime_s'] / 60:.1f} min"), ("API version", health["version"]),
    ]
    body = "".join(f"<div><dt>{escape(k)}</dt><dd class='data'>{escape(str(v))}</dd></div>" for k, v in rows)
    extra = ""
    if health.get("error"):
        extra += notice("error", "Model error", f"<div>{escape(health['error'])}</div>")
    if health.get("mock"):
        extra += notice("warn", "Mock detector active", "<div>Detections are simulated. Not for operational use.</div>")
    return f"<dl class='kv'>{body}</dl>{extra}"


# ---------------------------------------------------------------- relay mode HUD
def relay_hud_html(stats: dict | None) -> str:
    if not stats:
        return "<div class='relay-hud'><span class='chip'>NO DATA</span></div>"
    live = stats["state"] == "live"
    label = {"live": "LIVE", "ended": "ENDED", "still": "STILL"}.get(stats["state"], "CONNECTING")
    threat = (
        "<span class='chip live'>THREAT DETECTED</span>" if stats.get("threat_active") else ""
    )
    return (
        f"<div class='relay-hud'><span class='chip {'live' if live else ''}'>{label}</span>"
        f"<span class='chip'>{stats['fps']:.1f} FPS</span>"
        f"<span class='chip'>{stats['width']}&times;{stats['height']}</span>"
        f"<span class='chip'>{escape(stats['name'])}</span>{threat}</div>"
    )


# ---------------------------------------------------------------- iframe components
_IFRAME_BASE = f"""
<link href="{FONT_LINK}" rel="stylesheet">
<style>
{TOKENS}
*{{box-sizing:border-box;margin:0}}
html,body{{height:100%;background:transparent;font-family:var(--font-ui);color:var(--text)}}
.data{{font-family:var(--font-data);font-variant-numeric:tabular-nums}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}}}
</style>
"""


def navbar_html(operator: str, role: str, health: dict | None) -> str:
    page = """
<style>
.bar{height:100%;display:flex;align-items:center;gap:20px;padding:0 4px;border-bottom:1px solid var(--line);background:var(--bg)}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:16px;letter-spacing:.01em}
.brand svg{color:var(--cyan)}
.grow{flex:1}
.status{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;font-size:12.5px;
  background:var(--panel);border:1px solid var(--line-2);color:var(--muted)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted)}
.status[data-s=ok] .dot{background:var(--green)} .status[data-s=ok]{color:var(--text)}
.status[data-s=warn] .dot{background:var(--amber)} .status[data-s=warn]{color:var(--amber-text)}
.status[data-s=down] .dot{background:var(--red)} .status[data-s=down]{color:var(--red-text)}
.user{display:flex;align-items:center;gap:10px;font-size:13px;line-height:1.25}
.user .av{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:var(--cyan-dim);
  color:var(--cyan);border:1px solid var(--cyan);font-weight:600;font-size:12px}
.user small{display:block;color:var(--muted);font-size:11.5px}
.clock{text-align:right;line-height:1.2;padding-left:16px;border-left:1px solid var(--line)}
.clock b{display:block;font-size:17px;font-weight:500}
.clock small{color:var(--muted);font-size:11.5px}
@media (max-width:720px){.user div,.clock small{display:none}.brand span{display:none}}
</style>
<div class="bar">
  <div class="brand">__LOGO__<span>Smart Vision</span></div>
  <div class="grow"></div>
  <div class="status" data-s="__STATUS__" role="status"><span class="dot"></span><span>__STATUS_TEXT__</span></div>
  <div class="user"><div class="av" id="av"></div><div><span id="un"></span><small id="ur"></small></div></div>
  <div class="clock"><b class="data" id="tm">--:--:--</b><small class="data" id="dt"></small></div>
</div>
<script>
const NAME = __NAME__, ROLE = __ROLE__;
const $ = id => document.getElementById(id);
$("un").textContent = NAME; $("ur").textContent = ROLE;
$("av").textContent = NAME.split(/\\s+/).slice(0,2).map(p => p[0]).join("").toUpperCase();
function tick(){
  const d = new Date();
  $("tm").textContent = d.toLocaleTimeString([], {hour12:false});
  $("dt").textContent = d.toLocaleDateString([], {weekday:"short", day:"2-digit", month:"short", year:"numeric"});
}
tick(); setInterval(tick, 1000);
</script>
"""
    if health is None:
        status, status_text = "down", "Backend offline"
    elif health.get("mock"):
        status, status_text = "warn", "Backend online · mock detector"
    elif health.get("model_loaded"):
        status, status_text = "ok", "Backend online · model ready"
    else:
        status, status_text = "warn", "Backend online · model not loaded"
    page = (
        page.replace("__LOGO__", icon("logo", 26))
        .replace("__STATUS__", status)
        .replace("__STATUS_TEXT__", escape(status_text))
        .replace("__NAME__", _js(operator))
        .replace("__ROLE__", _js(role))
    )
    return f"<!doctype html><html><head><meta charset='utf-8'>{_IFRAME_BASE}</head><body>{page}</body></html>"


def stage_html(api_url: str, source: dict | None, stream_url: str | None, image_url: str | None) -> str:
    """CCTV stage: the image element points straight at the MJPEG endpoint, so the browser renders frames
    natively with no Streamlit reruns; HUD values are polled from /stats by a small script."""
    page = """
<style>
.stage{position:relative;height:100%;background:#03060D;border:1px solid var(--line);border-radius:12px;overflow:hidden;
  transition:border-color .2s var(--ease)}
.stage[data-threat="1"]{border-color:var(--red)}
#feed{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;display:block}
.hud{position:absolute;display:flex;gap:8px;align-items:center;pointer-events:none;z-index:2}
.tl{top:16px;left:16px}.tr{top:16px;right:16px}.bl{bottom:16px;left:16px}.br{bottom:16px;right:16px}
.chip{display:inline-flex;align-items:center;gap:7px;padding:5px 10px;border-radius:6px;background:rgba(7,11,22,.82);
  border:1px solid var(--line-2);font:500 12px/1 var(--font-data);color:var(--text);font-variant-numeric:tabular-nums}
.chip.badge{font-weight:500;letter-spacing:.06em}
.stage[data-state=live] .badge{background:rgba(239,68,68,.2);border-color:var(--red);color:var(--red-text)}
.stage[data-state=live] .badge i{width:8px;height:8px;border-radius:50%;background:var(--red);animation:blink 1.4s ease-in-out infinite}
.stage[data-state=still] .badge{border-color:var(--cyan);color:var(--cyan)}
.stage[data-state=error] .badge{border-color:var(--amber);color:var(--amber-text)}
.badge i{width:8px;height:8px;border-radius:50%;background:var(--muted)}
@keyframes blink{50%{opacity:.25}}
.corner{position:absolute;width:26px;height:26px;border:2px solid var(--cyan);z-index:1;pointer-events:none;opacity:.9;
  transition:border-color .2s var(--ease)}
.c1{top:10px;left:10px;border-right:0;border-bottom:0}.c2{top:10px;right:10px;border-left:0;border-bottom:0}
.c3{bottom:10px;left:10px;border-right:0;border-top:0}.c4{bottom:10px;right:10px;border-left:0;border-top:0}
.stage[data-threat="1"] .corner{border-color:var(--red)}
.banner{position:absolute;left:50%;bottom:20px;transform:translate(-50%,12px);opacity:0;z-index:3;pointer-events:none;
  padding:9px 16px;border-radius:8px;background:var(--red);color:var(--on-red);font-weight:600;font-size:13px;
  letter-spacing:.04em;box-shadow:0 8px 24px rgba(0,0,0,.5);transition:opacity .2s var(--ease),transform .2s var(--ease)}
.stage[data-threat="1"] .banner{opacity:1;transform:translate(-50%,0)}
.overlay{position:absolute;inset:0;z-index:2;display:none;flex-direction:column;align-items:center;justify-content:center;
  gap:10px;text-align:center;padding:24px;color:var(--muted)}
.stage[data-state=standby] .overlay,.stage[data-state=error] .overlay{display:flex}
.overlay svg{color:var(--line-2)}
.overlay b{color:var(--text);font-size:15px;font-weight:600}
.overlay p{max-width:44ch;font-size:13px;line-height:1.55}
.stage[data-state=error] .overlay svg{color:var(--amber)}
.stage[data-state=standby] #feed,.stage[data-state=error] #feed{visibility:hidden}
</style>
<div class="stage" id="stage" data-state="__INIT__" data-threat="0">
  __IMG__
  <span class="corner c1"></span><span class="corner c2"></span><span class="corner c3"></span><span class="corner c4"></span>
  <div class="hud tl"><span class="chip badge"><i></i><span id="badge">__BADGE__</span></span><span class="chip" id="cam"></span></div>
  <div class="hud tr"><span class="chip" id="fps">-- FPS</span><span class="chip" id="res">----&times;----</span></div>
  <div class="hud bl"><span class="chip" id="ts"></span></div>
  <div class="hud br"><span class="chip" id="det">DET 0</span></div>
  <div class="banner" id="banner" role="alert">THREAT DETECTED</div>
  <div class="overlay" id="overlay">__CAM_OFF__<b id="ov-t"></b><p id="ov-b"></p></div>
</div>
<script>
const API = __API__, SID = __SID__, KIND = __KIND__, NAME = __NAME__;
const $ = id => document.getElementById(id);
const stage = $("stage"), feed = $("feed");
const LABEL = {live:"LIVE", still:"STILL", ended:"ENDED", standby:"NO SIGNAL", error:"OFFLINE", idle:"CONNECTING"};
function setState(s, title, body){
  stage.dataset.state = s; $("badge").textContent = LABEL[s] || s.toUpperCase();
  if(title !== undefined){ $("ov-t").textContent = title; $("ov-b").textContent = body; }
}
function clock(){ $("ts").textContent = new Date().toLocaleString([], {hour12:false}).replace(",", ""); }
clock(); setInterval(clock, 1000);
$("cam").textContent = SID ? NAME : "NO SOURCE";

if(!SID){
  setState("standby", "No feed connected", "Upload a video or image in the Source panel to start analysis.");
}else{
  let failures = 0;
  feed.addEventListener("error", () => setState("error", "Stream unavailable",
    "The browser could not load the feed from " + API + ". If the API is only reachable from the Streamlit server, enable relay mode in the Source panel."));
  async function poll(){
    try{
      const r = await fetch(API + "/api/sources/" + SID + "/stats", {cache:"no-store"});
      if(!r.ok) throw new Error(r.status);
      const s = await r.json(); failures = 0;
      if(stage.dataset.state !== "error") setState(s.state === "idle" ? "idle" : s.state);
      $("fps").textContent = KIND === "image" ? "STILL IMAGE" : s.fps.toFixed(1) + " FPS";
      $("res").textContent = s.width + "\\u00d7" + s.height;
      $("det").textContent = "DET " + s.detections.length;
      const threats = s.detections.filter(d => d.is_threat);
      stage.dataset.threat = threats.length ? "1" : "0";
      if(threats.length){
        const best = threats.reduce((a, b) => a.confidence >= b.confidence ? a : b);
        $("banner").textContent = "THREAT DETECTED \\u00b7 " + best.label.toUpperCase() + " " + Math.round(best.confidence * 100) + "%";
      }
    }catch(e){
      if(++failures >= 2) setState("error", "Lost connection to the backend", "Retrying automatically. Check that the API is running.");
    }
  }
  poll(); setInterval(poll, 400);
}
</script>
"""
    if source and stream_url and source["kind"] == "video":
        img = f"<img id='feed' alt='Live analysed camera feed' src={json.dumps(stream_url)}>"
    elif source and image_url:
        img = f"<img id='feed' alt='Analysed image' src={json.dumps(image_url)}>"
    else:
        img = ""  # standby: no media element, the overlay explains what to do
    init = "idle" if source else "standby"
    page = (
        page.replace("__IMG__", img)
        .replace("__INIT__", init)
        .replace("__BADGE__", "CONNECTING" if source else "NO SIGNAL")
        .replace("__CAM_OFF__", icon("camera-off", 44))
        .replace("__API__", _js(api_url))
        .replace("__SID__", _js(source["id"] if source else None))
        .replace("__KIND__", _js(source["kind"] if source else None))
        .replace("__NAME__", _js(source["name"] if source else ""))
    )
    return f"<!doctype html><html><head><meta charset='utf-8'>{_IFRAME_BASE}</head><body style='overflow:hidden'>{page}</body></html>"
