"""Design tokens and global CSS for the Smart Vision SOC console."""
from __future__ import annotations

FONT_LINK = (
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500"
    "&family=IBM+Plex+Sans:wght@400;500;600&display=swap"
)

# Shared by the Streamlit page and the iframe components (navbar, video stage).
TOKENS = """
:root{
  --bg:#070B16; --panel:#0C1324; --panel-2:#111B33; --line:#1A2644; --line-2:#2A3A62;
  --text:#E6EDF7; --muted:#93A4C3;
  --cyan:#38BDF8; --cyan-dim:rgba(56,189,248,.14); --on-cyan:#04101C;
  --red:#EF4444; --red-text:#FCA5A5; --red-dim:rgba(239,68,68,.14); --on-red:#070B16;
  --amber:#F59E0B; --amber-text:#FCD34D; --amber-dim:rgba(245,158,11,.14);
  --green:#34D399; --green-dim:rgba(52,211,153,.14);
  --font-ui:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --font-data:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --ease:cubic-bezier(.22,1,.36,1);
}
"""

CSS = f"""
<style>
@import url("{FONT_LINK}");
{TOKENS}

html, body, .stApp, button, input, textarea, select {{
  font-family: var(--font-ui) !important;
}}
.stApp {{ background: var(--bg); color: var(--text); }}
::selection {{ background: var(--cyan); color: var(--on-cyan); }}
* {{ caret-color: var(--cyan); scrollbar-width: thin; scrollbar-color: var(--line-2) transparent; }}
*::-webkit-scrollbar {{ width: 8px; height: 8px; }}
*::-webkit-scrollbar-thumb {{ background: var(--line-2); border-radius: 8px; }}
:focus-visible {{ outline: 2px solid var(--cyan) !important; outline-offset: 2px; }}

/* Streamlit chrome: hide on desktop, keep the sidebar toggle on narrow screens */
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
#MainMenu, footer {{ display: none !important; }}
@media (min-width: 992px) {{
  header[data-testid="stHeader"], [data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
}}
@media (max-width: 991px) {{ header[data-testid="stHeader"] {{ background: var(--bg); }} }}

[data-testid="stMainBlockContainer"], .block-container {{
  padding: 0 1.25rem 2rem 1.25rem !important; max-width: 100% !important;
}}
iframe {{ border: 0 !important; color-scheme: dark; }}

/* Sidebar */
[data-testid="stSidebar"] {{ background: var(--panel); border-right: 1px solid var(--line); }}
[data-testid="stSidebar"] > div:first-child {{ padding-top: .5rem; }}
[data-testid="stSidebarUserContent"] {{ padding: 1rem .75rem !important; }}

/* Navigation = styled radio group */
[data-testid="stRadio"] > label {{ display: none; }}
[data-testid="stRadio"] [role="radiogroup"] {{ gap: 2px; }}
[data-testid="stRadio"] label {{
  width: 100%; padding: .55rem .75rem; border-radius: 8px; cursor: pointer; color: var(--muted);
  display: flex; align-items: center; gap: .7rem; transition: background .18s var(--ease), color .18s var(--ease);
}}
[data-testid="stRadio"] label > div:first-child {{ display: none !important; }}
[data-testid="stRadio"] label p {{ font-size: .9rem; font-weight: 500; color: inherit; margin: 0; }}
[data-testid="stRadio"] label::before {{
  content: ""; width: 18px; height: 18px; flex: none; background-color: currentColor;
  -webkit-mask: var(--ico) center / contain no-repeat; mask: var(--ico) center / contain no-repeat;
}}
[data-testid="stRadio"] label:nth-child(1) {{ --ico: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'><path d='M3 7h11a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H3z'/><path d='m16 10 5-3v10l-5-3'/></svg>"); }}
[data-testid="stRadio"] label:nth-child(2) {{ --ico: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'><path d='M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01'/></svg>"); }}
[data-testid="stRadio"] label:nth-child(3) {{ --ico: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'><path d='M22 12h-4l-3 9L9 3l-3 9H2'/></svg>"); }}
[data-testid="stRadio"] label:hover {{ background: var(--panel-2); color: var(--text); }}
[data-testid="stRadio"] label:has(input:checked) {{ background: var(--cyan-dim); color: var(--cyan); }}

/* Profile card */
.profile {{ display: flex; align-items: center; gap: .75rem; padding: .75rem; margin-bottom: 1rem;
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 10px; }}
.avatar {{ width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; flex: none;
  background: var(--cyan-dim); color: var(--cyan); border: 1px solid var(--cyan); font-weight: 600; font-size: .85rem; }}
.profile b {{ display: block; font-size: .9rem; font-weight: 600; }}
.profile span {{ display: block; font-size: .78rem; color: var(--muted); }}
.side-foot {{ margin-top: 1.5rem; font-size: .75rem; color: var(--muted); line-height: 1.6; }}
.side-foot .data {{ color: var(--text); }}

/* Panels = bordered containers */
[data-testid="stVerticalBlockBorderWrapper"] {{
  background: var(--panel); border: 1px solid var(--line) !important; border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0,0,0,.35);
}}
.panel-title {{ display: flex; align-items: center; gap: .5rem; margin: 0 0 .6rem 0; font-size: .86rem;
  font-weight: 600; letter-spacing: .01em; color: var(--text); }}
.panel-title svg {{ width: 16px; height: 16px; color: var(--cyan); flex: none; }}
.panel-title .aside {{ margin-left: auto; font: 400 .75rem var(--font-data); color: var(--muted); }}
.muted {{ color: var(--muted); }}
.data {{ font-family: var(--font-data); font-variant-numeric: tabular-nums; }}

/* Buttons */
.stButton > button {{
  width: 100%; border-radius: 8px; border: 1px solid var(--line-2); background: var(--panel-2);
  color: var(--text); font-weight: 500; padding: .55rem .9rem; transition: background .18s var(--ease), border-color .18s var(--ease);
}}
.stButton > button:hover {{ border-color: var(--cyan); background: var(--cyan-dim); color: var(--text); }}
.stButton > button:disabled {{ opacity: .45; cursor: not-allowed; }}
.stButton > button[kind="primary"] {{ background: var(--cyan); color: var(--on-cyan); border-color: var(--cyan); font-weight: 600; }}
.st-key-panic_arm button, .st-key-panic_confirm button {{
  background: var(--red); border-color: var(--red); color: var(--on-red); font-weight: 600; }}
.st-key-panic_arm button:hover, .st-key-panic_confirm button:hover {{ background: #F87171; border-color: #F87171; color: var(--on-red); }}

/* Uploader */
[data-testid="stFileUploaderDropzone"] {{
  background: var(--bg); border: 1px dashed var(--line-2); border-radius: 10px; transition: border-color .18s var(--ease);
}}
[data-testid="stFileUploaderDropzone"]:hover {{ border-color: var(--cyan); }}
[data-testid="stFileUploaderDropzone"] button {{ background: var(--panel-2); color: var(--text); border: 1px solid var(--line-2); }}
[data-testid="stFileUploaderDropzone"] small, [data-testid="stFileUploaderDropzoneInstructions"] {{ color: var(--muted) !important; }}
[data-testid="stFileUploader"] label p {{ color: var(--text); font-size: .85rem; }}
[data-testid="stToggle"] p, [data-testid="stCheckbox"] p {{ color: var(--muted); font-size: .8rem; }}

/* Streamlit native images (relay mode) */
[data-testid="stImage"] img {{ width: 100%; border-radius: 10px; border: 1px solid var(--line); background: #03060D; }}

/* Key/value list (telemetry, system) */
.kv {{ margin: 0; display: grid; gap: .6rem; }}
.kv > div {{ display: flex; justify-content: space-between; align-items: baseline; gap: 1rem;
  padding-bottom: .6rem; border-bottom: 1px solid var(--line); }}
.kv > div:last-child {{ border-bottom: 0; padding-bottom: 0; }}
.kv dt {{ color: var(--muted); font-size: .82rem; }}
.kv dd {{ margin: 0; text-align: right; font-size: .88rem; }}
.kv dd.big {{ font-size: 1.5rem; font-weight: 500; line-height: 1; }}
.kv dd.crit {{ color: var(--red-text); }}

/* Alerts feed */
.alerts {{ list-style: none; margin: 0; padding: 0; max-height: 300px; overflow-y: auto; display: grid; gap: 6px; }}
.alert {{ display: grid; grid-template-columns: 18px 1fr auto; gap: .6rem; align-items: start;
  padding: .6rem .7rem; border-radius: 8px; background: var(--panel-2); border: 1px solid var(--line); }}
.alert svg {{ width: 18px; height: 18px; margin-top: 1px; }}
.alert.critical {{ background: var(--red-dim); border-color: rgba(239,68,68,.45); }}
.alert.critical svg, .alert.critical .a-msg {{ color: var(--red-text); }}
.alert.warning svg, .alert.warning .a-msg {{ color: var(--amber-text); }}
.alert.info svg {{ color: var(--cyan); }}
.a-msg {{ margin: 0; font-size: .85rem; font-weight: 500; }}
.a-meta {{ margin: 2px 0 0; font-size: .75rem; color: var(--muted); overflow-wrap: anywhere; }}
.a-ago {{ font: 400 .72rem var(--font-data); color: var(--muted); white-space: nowrap; }}

/* Empty / notice states */
.empty {{ padding: 1rem; border: 1px dashed var(--line-2); border-radius: 10px; color: var(--muted); font-size: .84rem; line-height: 1.5; }}
.empty b {{ display: block; color: var(--text); font-weight: 500; margin-bottom: .2rem; }}
.notice {{ padding: .75rem .9rem; border-radius: 10px; font-size: .85rem; line-height: 1.5; border: 1px solid var(--line-2); background: var(--panel-2); }}
.notice b {{ display: block; font-weight: 600; margin-bottom: .15rem; }}
.notice.error {{ background: var(--red-dim); border-color: rgba(239,68,68,.5); color: var(--red-text); }}
.notice.warn {{ background: var(--amber-dim); border-color: rgba(245,158,11,.5); color: var(--amber-text); }}
.notice.ok {{ background: var(--green-dim); border-color: rgba(52,211,153,.45); color: var(--green); }}
.notice code {{ font-family: var(--font-data); font-size: .8rem; background: rgba(0,0,0,.35); padding: 1px 5px; border-radius: 4px; }}

/* Panic widget */
.link-row {{ display: flex; align-items: center; gap: .55rem; font-size: .84rem; margin-bottom: .75rem; }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--muted); flex: none; }}
.dot.ok {{ background: var(--green); }} .dot.warn {{ background: var(--amber); }} .dot.bad {{ background: var(--red); }}
.confirm-copy {{ font-size: .8rem; color: var(--red-text); margin: 0 0 .5rem; }}

/* Tables */
.tbl {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
.tbl th {{ text-align: left; color: var(--muted); font-weight: 500; padding: .55rem .75rem; border-bottom: 1px solid var(--line-2); }}
.tbl td {{ padding: .6rem .75rem; border-bottom: 1px solid var(--line); }}
.tbl tr:hover td {{ background: var(--panel-2); }}
.pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: .72rem; font-weight: 500; }}
.pill.critical {{ background: var(--red-dim); color: var(--red-text); }}
.pill.warning {{ background: var(--amber-dim); color: var(--amber-text); }}
.pill.info {{ background: var(--cyan-dim); color: var(--cyan); }}
.page-title {{ font-size: 1.15rem; font-weight: 600; margin: 1rem 0 .25rem; }}
.page-sub {{ color: var(--muted); font-size: .86rem; margin: 0 0 1rem; max-width: 70ch; }}

/* Relay-mode HUD bar */
.relay-hud {{ display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: .5rem; }}
.chip {{ display: inline-flex; align-items: center; gap: .4rem; padding: 4px 10px; border-radius: 6px;
  font: 500 .75rem var(--font-data); background: var(--panel-2); border: 1px solid var(--line-2); color: var(--text); }}
.chip.live {{ background: var(--red-dim); border-color: rgba(239,68,68,.55); color: var(--red-text); }}

@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""
