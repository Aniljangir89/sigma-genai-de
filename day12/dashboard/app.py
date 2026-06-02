"""
Sigma Command Center — Business Incident Dashboard
===================================================
Reads from Azure Blob Storage + local agent_outputs/ fallback.
All 7 sections: KPI Cards, Agent Status, Timeline, Root Cause,
Recovery Summary, Prevention Alarms, Full Incident Report.

Run:  streamlit run dashboard/app.py
"""

import io
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# ── Load env ──────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent   # day12/
load_dotenv(_ROOT / "lab" / ".env")

AZURE_CONN    = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
REGION        = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AGENT_OUTPUTS = _ROOT / "lab" / "agent_outputs"

# ── Session state defaults ────────────────────────────────────────────────────
if "last_refresh"    not in st.session_state:
    st.session_state.last_refresh    = time.time()
if "data_fingerprint" not in st.session_state:
    st.session_state.data_fingerprint = ""
if "new_data_flag"   not in st.session_state:
    st.session_state.new_data_flag   = False

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Sigma Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Injected CSS — dark glassmorphism theme ───────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Dark background */
.stApp {
    background: linear-gradient(135deg, #0a0e1a 0%, #0d1321 40%, #111827 100%);
    color: #e2e8f0;
}

/* Hide default Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* ── KPI Cards ── */
.kpi-card {
    background: linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 16px;
    padding: 1.4rem 1.2rem;
    backdrop-filter: blur(10px);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    text-align: center;
    margin-bottom: 0.5rem;
}
.kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 12px 40px rgba(0,0,0,0.4);
}
.kpi-value {
    font-size: 2.4rem;
    font-weight: 900;
    line-height: 1.1;
    margin: 0.3rem 0;
}
.kpi-label {
    font-size: 0.75rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94a3b8;
    margin-top: 0.4rem;
}
.kpi-delta {
    font-size: 0.72rem;
    margin-top: 0.25rem;
    opacity: 0.7;
}

/* ── Section headings ── */
.section-title {
    font-size: 1.05rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #94a3b8;
    margin: 1.6rem 0 0.8rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding-bottom: 0.5rem;
}

/* ── Agent status cards ── */
.agent-card {
    border-radius: 12px;
    padding: 1rem 1.1rem;
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(6px);
    margin-bottom: 0.4rem;
}
.agent-name  { font-weight: 700; font-size: 0.9rem; margin-bottom: 0.15rem; }
.agent-find  { font-size: 0.75rem; color: #94a3b8; line-height: 1.4; }
.status-done { background: linear-gradient(135deg, rgba(16,185,129,0.18), rgba(16,185,129,0.06)); border-color: rgba(16,185,129,0.35); }
.status-run  { background: linear-gradient(135deg, rgba(245,158,11,0.18), rgba(245,158,11,0.06)); border-color: rgba(245,158,11,0.35); }
.status-fail { background: linear-gradient(135deg, rgba(239,68,68,0.18),  rgba(239,68,68,0.06));  border-color: rgba(239,68,68,0.35);  }

/* ── Timeline ── */
.tl-row {
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    margin-bottom: 0.8rem;
}
.tl-dot {
    width: 12px; height: 12px;
    border-radius: 50%;
    margin-top: 5px;
    flex-shrink: 0;
}
.tl-ts   { font-size: 0.72rem; color: #64748b; font-family: monospace; white-space: nowrap; min-width: 110px; margin-top: 3px; }
.tl-text { font-size: 0.85rem; color: #cbd5e1; line-height: 1.5; }
.dot-critical { background: #ef4444; box-shadow: 0 0 8px #ef4444; }
.dot-warning  { background: #f59e0b; box-shadow: 0 0 8px #f59e0b; }
.dot-info     { background: #3b82f6; box-shadow: 0 0 8px #3b82f6; }
.dot-success  { background: #10b981; box-shadow: 0 0 8px #10b981; }

/* ── Root cause panel ── */
.root-cause-box {
    background: linear-gradient(135deg, rgba(239,68,68,0.12), rgba(239,68,68,0.04));
    border: 1px solid rgba(239,68,68,0.35);
    border-left: 4px solid #ef4444;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
}
.root-cause-box p { color: #fca5a5; font-size: 0.9rem; line-height: 1.7; margin: 0; }

.success-box {
    background: linear-gradient(135deg, rgba(16,185,129,0.12), rgba(16,185,129,0.04));
    border: 1px solid rgba(16,185,129,0.35);
    border-left: 4px solid #10b981;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
}
.success-box p { color: #6ee7b7; font-size: 0.9rem; line-height: 1.7; margin: 0; }

/* ── Recovery bar ── */
.rec-bar-wrap { background: rgba(255,255,255,0.06); border-radius: 999px; height: 12px; overflow: hidden; }
.rec-bar-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #10b981, #34d399); }

/* ── Alarm chips ── */
.alarm-chip {
    border-radius: 10px;
    padding: 0.9rem 1rem;
    border: 1px solid rgba(255,255,255,0.08);
    backdrop-filter: blur(6px);
    margin-bottom: 0.4rem;
}
.alarm-name { font-weight: 700; font-size: 0.82rem; }
.alarm-desc { font-size: 0.72rem; color: #94a3b8; margin-top: 0.2rem; line-height: 1.4; }
.alarm-ok   { background: linear-gradient(135deg, rgba(16,185,129,0.15),rgba(16,185,129,0.04)); border-color: rgba(16,185,129,0.3); }
.alarm-warn { background: linear-gradient(135deg, rgba(245,158,11,0.15),rgba(245,158,11,0.04)); border-color: rgba(245,158,11,0.3); }
.alarm-off  { background: linear-gradient(135deg, rgba(100,116,139,0.15),rgba(100,116,139,0.04)); border-color: rgba(100,116,139,0.25); }

/* ── Report expander ── */
.incident-report-box {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 1.5rem 1.8rem;
}

/* ── Header banner ── */
.header-band {
    background: linear-gradient(90deg, rgba(239,68,68,0.2), rgba(99,102,241,0.15), rgba(16,185,129,0.1));
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 14px;
    padding: 1.4rem 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.2rem;
}
.header-title { font-size: 1.6rem; font-weight: 900; letter-spacing: -0.02em; }
.header-sub   { font-size: 0.78rem; color: #94a3b8; margin-top: 0.2rem; }

/* ── Streamlit override ── */
div[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
.stDataFrame { background: rgba(255,255,255,0.03); }

/* ── Divider ── */
hr { border-color: rgba(255,255,255,0.07); margin: 1.2rem 0; }

/* ── Progress bars ── */
.stProgress > div > div { background: linear-gradient(90deg, #6366f1, #8b5cf6); border-radius: 999px; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: rgba(10,14,26,0.97);
    border-right: 1px solid rgba(255,255,255,0.07);
}

/* ── NEW badge ── */
.new-badge {
    display: inline-block;
    background: linear-gradient(90deg, #ef4444, #f97316);
    color: white;
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    padding: 0.15rem 0.5rem;
    border-radius: 999px;
    animation: pulse-badge 1s ease-in-out infinite;
    margin-left: 0.5rem;
    vertical-align: middle;
}
@keyframes pulse-badge {
    0%,100% { opacity: 1; transform: scale(1); }
    50%      { opacity: 0.7; transform: scale(1.08); }
}

/* ── Countdown bar ── */
.cd-wrap { background: rgba(255,255,255,0.05); border-radius: 999px; height: 4px; margin-top: 0.4rem; overflow: hidden; }
.cd-fill  { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #6366f1, #8b5cf6); transition: width 1s linear; }

/* ── Live dot ── */
.live-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 6px #10b981;
    animation: blink 1.4s ease-in-out infinite;
    margin-right: 6px;
    vertical-align: middle;
}
@keyframes blink {
    0%,100% { opacity: 1; } 50% { opacity: 0.3; }
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — AUTO-REFRESH CONTROLS
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style='font-size:1.1rem;font-weight:800;letter-spacing:-0.01em;margin-bottom:0.2rem'>
        ⚡ Sigma Command Center
    </div>
    <div style='font-size:0.72rem;color:#64748b;margin-bottom:1.2rem'>
        Self-Healing Intelligence Platform
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🔄 Auto-Refresh")
    st.markdown(
        "<div style='font-size:0.78rem;color:#94a3b8;margin-bottom:0.6rem'>"
        "Dashboard polls for new incident files and refreshes automatically "
        "when the timer fires.<br><br>"
        "<b>How it works:</b> Every N seconds, the app checks if a new "
        "<code>incident_*.md</code> or <code>quarantine_*.csv</code> file "
        "appeared in Azure Blob Storage or <code>agent_outputs/</code>. "
        "If the file list changed, it clears the cache and re-renders with fresh data."
        "</div>",
        unsafe_allow_html=True
    )

    refresh_options = {"Off": 0, "10 seconds": 10, "30 seconds": 30,
                       "60 seconds": 60, "2 minutes": 120}
    chosen_label    = st.selectbox(
        "Refresh interval",
        list(refresh_options.keys()),
        index=2,            # default: 30 seconds
        key="refresh_sel"
    )
    refresh_interval = refresh_options[chosen_label]

    if refresh_interval > 0:
        elapsed  = time.time() - st.session_state.last_refresh
        remaining = max(0, refresh_interval - elapsed)
        pct_done  = min(100, elapsed / refresh_interval * 100)

        st.markdown(
            f"<div style='font-size:0.75rem;color:#94a3b8;margin-top:0.6rem'>"
            f"<span class='live-dot'></span>Next refresh in "
            f"<b>{remaining:.0f}s</b></div>"
            f"<div class='cd-wrap'><div class='cd-fill' style='width:{pct_done:.1f}%'></div></div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            "<div style='font-size:0.75rem;color:#475569;margin-top:0.4rem'>"
            "Auto-refresh is OFF — use the Refresh button.</div>",
            unsafe_allow_html=True
        )

    st.markdown("---")

    if st.button("🔄 Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_refresh    = time.time()
        st.session_state.new_data_flag   = False
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ Data Sources")
    st.markdown(
        "<div style='font-size:0.75rem;color:#94a3b8;line-height:1.7'>"
        "📦 <b>Incident report:</b><br>Azure Blob <code>reports/</code><br>"
        "→ fallback: <code>agent_outputs/</code><br><br>"
        "📦 <b>Quarantine CSV:</b><br>Azure Blob <code>quarantine/</code><br>"
        "→ fallback: <code>agent_outputs/</code><br><br>"
        "📡 <b>Alarm states:</b><br>AWS CloudWatch (boto3)<br>"
        "→ fallback: <code>alarms_created.json</code>"
        "</div>",
        unsafe_allow_html=True
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DATA FINGERPRINT — detects when new files appear
# ═══════════════════════════════════════════════════════════════════════════════

def get_data_fingerprint() -> str:
    """
    Returns a short string that changes whenever new incident/quarantine
    files appear — either in Azure Blob Storage or local agent_outputs/.
    If the fingerprint differs from the last render, new data is available.
    """
    parts = []

    # Local files (always fast)
    if AGENT_OUTPUTS.exists():
        md_files  = sorted(AGENT_OUTPUTS.glob("incident_*.md"),   key=lambda p: p.stat().st_mtime, reverse=True)
        csv_files = sorted(AGENT_OUTPUTS.glob("quarantine_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if md_files:  parts.append(f"local_md:{md_files[0].name}")
        if csv_files: parts.append(f"local_csv:{csv_files[0].name}")

    # Azure Blob Storage (try quickly)
    if AZURE_CONN:
        try:
            from azure.storage.blob import BlobServiceClient
            blob_svc = BlobServiceClient.from_connection_string(AZURE_CONN)
            rblobs = sorted(
                list(blob_svc.get_container_client("reports").list_blobs()),
                key=lambda b: b.last_modified, reverse=True
            )
            if rblobs: parts.append(f"az_md:{rblobs[0].name}")
        except Exception:
            pass

    return "|".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-REFRESH TRIGGER
# ═══════════════════════════════════════════════════════════════════════════════

if refresh_interval > 0:
    elapsed = time.time() - st.session_state.last_refresh

    # Always schedule a re-run so the countdown bar updates
    # st.rerun() after sleep would block — use fragment-free approach:
    # Streamlit will re-run whenever session state changes or time.sleep fires.
    if elapsed >= refresh_interval:
        # Check fingerprint before clearing cache
        current_fp = get_data_fingerprint()
        if current_fp != st.session_state.data_fingerprint:
            st.session_state.new_data_flag   = True
            st.session_state.data_fingerprint = current_fp

        st.cache_data.clear()
        st.session_state.last_refresh = time.time()
        st.rerun()
    else:
        # Sleep for the remainder of the interval in small chunks
        # so the countdown bar animates. Sleep 1s then rerun.
        time.sleep(1)
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

# Update fingerprint on first load
_current_fp = get_data_fingerprint()
if not st.session_state.data_fingerprint:
    st.session_state.data_fingerprint = _current_fp
elif _current_fp != st.session_state.data_fingerprint:
    st.session_state.new_data_flag    = True
    st.session_state.data_fingerprint = _current_fp

@st.cache_data(ttl=30)
def load_data() -> dict:
    """
    Load all incident data.
    Priority: Azure Blob Storage → local agent_outputs/ fallback.
    CloudWatch alarm states always come from AWS (boto3).
    """

    report_md   = ""
    report_key  = ""
    findings    = {}
    quarantine_df = pd.DataFrame()
    alarms      = []

    # ── 1. Try Azure Blob Storage ─────────────────────────────────────────────
    azure_ok = False
    if AZURE_CONN:
        try:
            from azure.storage.blob import BlobServiceClient
            blob_svc = BlobServiceClient.from_connection_string(AZURE_CONN)

            # Incident report (markdown)
            try:
                container = blob_svc.get_container_client("reports")
                blobs     = sorted(
                    list(container.list_blobs(name_starts_with="incident_")),
                    key=lambda b: b.last_modified, reverse=True
                )
                if blobs:
                    latest     = blobs[0]
                    report_key = latest.name
                    report_md  = container.download_blob(latest.name).readall().decode("utf-8")
                    azure_ok   = True
            except Exception:
                pass

            # Quarantine CSV
            try:
                qcontainer = blob_svc.get_container_client("quarantine")
                qblobs     = sorted(
                    [b for b in qcontainer.list_blobs()],
                    key=lambda b: b.last_modified, reverse=True
                )
                if qblobs:
                    csv_raw = qcontainer.download_blob(qblobs[0].name).readall().decode("utf-8")
                    quarantine_df = pd.read_csv(io.StringIO(csv_raw))
            except Exception:
                pass

        except Exception:
            pass

    # ── 2. Fallback to local agent_outputs/ ───────────────────────────────────
    if not azure_ok and AGENT_OUTPUTS.exists():
        # incident markdown
        md_files = sorted(AGENT_OUTPUTS.glob("incident_*.md"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        if md_files:
            report_key = md_files[0].name
            report_md  = md_files[0].read_text(encoding="utf-8")

        # incident JSON for richer data
        json_files = sorted(AGENT_OUTPUTS.glob("incident_*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if json_files:
            findings = json.loads(json_files[0].read_text(encoding="utf-8"))

        # quarantine CSV
        csv_files = sorted(AGENT_OUTPUTS.glob("quarantine_*.csv"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        if csv_files:
            quarantine_df = pd.read_csv(csv_files[0])

    # If we have azure report but no JSON, try local JSON
    if azure_ok and not findings and AGENT_OUTPUTS.exists():
        json_files = sorted(AGENT_OUTPUTS.glob("incident_*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if json_files:
            findings = json.loads(json_files[0].read_text(encoding="utf-8"))

    # ── 3. CloudWatch alarm states ────────────────────────────────────────────
    alarm_names = [
        "sigma-snowflake-zero-load",
        "sigma-lambda-version-change",
        "sigma-pipeline-row-divergence",
    ]
    try:
        cw   = boto3.client("cloudwatch", region_name=REGION)
        resp = cw.describe_alarms(AlarmNames=alarm_names)
        alarms = [
            {
                "name":    a["AlarmName"],
                "trigger": a.get("AlarmDescription", "—"),
                "state":   a["StateValue"],
            }
            for a in resp.get("MetricAlarms", [])
        ]
    except Exception:
        # fallback: local alarms_created.json
        local_alarms = AGENT_OUTPUTS / "alarms_created.json"
        if local_alarms.exists():
            data = json.loads(local_alarms.read_text(encoding="utf-8"))
            alarms = [
                {
                    "name":    a["alert_name"],
                    "trigger": a.get("description", "—"),
                    "state":   "INSUFFICIENT_DATA",
                }
                for a in data.get("alarms", [])
            ]

    return {
        "report_md":      report_md,
        "report_key":     report_key,
        "findings":       findings,
        "quarantine_df":  quarantine_df,
        "alarms":         alarms,
        "azure_source":   azure_ok,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def kpi_card(label: str, value: str, color: str, delta: str = ""):
    delta_html = f'<div class="kpi-delta">{delta}</div>' if delta else ""
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color:{color}">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def agent_card(icon: str, name: str, status: str, finding: str):
    css = {"complete": "status-done", "running": "status-run", "failed": "status-fail"}.get(status, "status-off")
    st.markdown(f"""
    <div class="agent-card {css}">
        <div class="agent-name">{icon} {name}</div>
        <div class="agent-find">{finding}</div>
    </div>
    """, unsafe_allow_html=True)


def timeline_event(ts: str, text: str, severity: str):
    dot_cls = f"dot-{severity}"
    st.markdown(f"""
    <div class="tl-row">
        <div class="tl-ts">{ts}</div>
        <div><div class="tl-dot {dot_cls}"></div></div>
        <div class="tl-text">{text}</div>
    </div>
    """, unsafe_allow_html=True)


def alarm_chip(name: str, trigger: str, state: str):
    if state == "OK":
        css, icon = "alarm-ok", "🟢"
    elif state == "ALARM":
        css, icon = "alarm-warn", "🔴"
    else:
        css, icon = "alarm-off", "🟡"
    st.markdown(f"""
    <div class="alarm-chip {css}">
        <div class="alarm-name">{icon} {name}</div>
        <div class="alarm-desc">{trigger}</div>
        <div style="font-size:0.68rem;margin-top:0.3rem;color:#64748b;">State: {state}</div>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ═══════════════════════════════════════════════════════════════════════════════

with st.spinner("Loading incident data..."):
    data = load_data()

f = data["findings"]
recovery  = f.get("recovery",  {})
impact    = f.get("impact",    {})
forensics = f.get("forensics", {})
hardening = f.get("hardening", {})
agents_perf = f.get("agent_performance", [])

records_missing    = impact.get("records_missing", 847)
records_recovered  = recovery.get("rows_loaded", 824)
records_quarantine = recovery.get("quarantined_count", 23)
gmv_gap            = impact.get("gmv_gap_inr", "₹4,72,340")
recovery_time_sec  = sum(a.get("duration_sec", 0) for a in agents_perf) or 26


# ═══════════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════════

src_label  = "Azure Blob Storage" if data["azure_source"] else "Local agent_outputs/"
ts_refresh = datetime.now().strftime("%H:%M:%S")

# New-data badge
new_badge  = "<span class='new-badge'>🆕 NEW DATA</span>" if st.session_state.new_data_flag else ""
live_label = f"<span class='live-dot'></span>LIVE" if refresh_interval > 0 else "STATIC"

st.markdown(f"""
<div class="header-band">
  <div>
    <div class="header-title">⚡ Sigma Command Center {new_badge}</div>
    <div class="header-sub">
      {live_label} &nbsp;·&nbsp;
      Source: <strong>{src_label}</strong> &nbsp;·&nbsp;
      Last refresh: <strong>{ts_refresh}</strong> &nbsp;·&nbsp;
      Interval: <strong>{chosen_label}</strong>
    </div>
  </div>
  <div style="text-align:right">
    <div style="font-size:2rem">🔴 RESOLVED</div>
    <div style="font-size:0.7rem;color:#94a3b8;margin-top:0.1rem">Autonomous recovery complete</div>
  </div>
</div>
""", unsafe_allow_html=True)

# Clear new_data_flag after showing it
if st.session_state.new_data_flag:
    st.session_state.new_data_flag = False


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — KPI CARDS
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-title">📊 Incident KPIs</div>', unsafe_allow_html=True)

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    kpi_card("Expected Transactions", "1,20,000", "#e2e8f0", "Baseline (yesterday)")
with c2:
    kpi_card("Actual Transactions", "40,000", "#f87171", "Dashboard showed this")
with c3:
    kpi_card("Missing Transactions", f"{records_missing:,}", "#fb923c", "Gap detected at 09:03")
with c4:
    kpi_card("Records Recovered", f"{records_recovered:,}", "#34d399", "Idempotent replay ✓")
with c5:
    kpi_card("Quarantined", f"{records_quarantine:,}", "#a78bfa", "Null PKs — preserved")
with c6:
    kpi_card("Recovery Time", f"{recovery_time_sec}s", "#60a5fa", "Human interventions: 0")

st.markdown("<hr/>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — AGENT STATUS PANEL + INCIDENT TIMELINE (side by side)
# ═══════════════════════════════════════════════════════════════════════════════

col_agents, col_timeline = st.columns([2, 3], gap="large")

with col_agents:
    st.markdown('<div class="section-title">🤖 Agent Status</div>', unsafe_allow_html=True)

    agent_findings = {
        "Forensics":      ("🔍", "Lambda v2 deploy at 02:11 UTC — schema mismatch identified"),
        "Impact":         ("💰", f"GMV gap {gmv_gap} · QuickMart SLA breached"),
        "Recovery":       ("♻️", f"{records_recovered} records replayed · 0 duplicates"),
        "Rollback":       ("⏪", "v2 → v1 in 8 sec · test records confirmed stable"),
        "Hardening":      ("🛡️", "3 CloudWatch alarms created and active"),
        "Incident Report":("📋", "CTO-ready post-mortem written to storage"),
    }

    # Derive status from findings JSON agent_performance
    completed_agents = {a["agent"] for a in agents_perf}

    for name, (icon, finding) in agent_findings.items():
        short = name.split()[0]  # "Forensics", "Recovery" etc.
        status = "complete" if short in completed_agents or short == "IncidentReport" else "running"
        agent_card(icon, name, status, finding)

with col_timeline:
    st.markdown('<div class="section-title">🕐 Incident Timeline</div>', unsafe_allow_html=True)

    timeline = [
        ("02:11 UTC",      "Azure Function auto-deployed to v2",                        "critical"),
        ("02:11 UTC",      "v2 renames merchant_name→merchant_nm · date format changed", "critical"),
        ("02:12 UTC",      "Firehose delivers malformed JSON to Blob Storage",           "warning"),
        ("02:12 UTC",      "Snowflake COPY INTO runs — loads 0 rows (schema mismatch)",  "critical"),
        ("02:12 UTC",      "Existing alarms do NOT fire (threshold too high)",           "warning"),
        ("09:03 UTC",      "Analytics manager reports: only 40,000 transactions visible","warning"),
        ("09:03 UTC",      "Supervisor Agent triggered by platform engineer",             "info"),
        ("09:03:04 UTC",   "MCP server discovered — 9 tools available",                  "info"),
        ("09:03:05 UTC",   "Forensics + Impact agents delegated in parallel",             "info"),
        ("09:03:09 UTC",   "Root cause confirmed: Lambda v2 schema drift",               "warning"),
        ("09:03:11 UTC",   "Rollback + Recovery delegated in parallel",                  "info"),
        ("09:03:13 UTC",   "Lambda rolled back to v1 · v1 stability confirmed",          "success"),
        ("09:03:18 UTC",   f"{records_recovered} records replayed · {records_quarantine} quarantined · 0 duplicates", "success"),
        ("09:03:19 UTC",   "3 CloudWatch alarms created and active",                     "success"),
        ("09:03:28 UTC",   f"GMV restored: {gmv_gap} · Recovery complete in {recovery_time_sec}s","success"),
    ]

    for ts, text, sev in timeline:
        timeline_event(ts, text, sev)

st.markdown("<hr/>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — ROOT CAUSE + SECTION 5 — RECOVERY SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════

col_rc, col_rec = st.columns(2, gap="large")

with col_rc:
    st.markdown('<div class="section-title">🔴 Root Cause</div>', unsafe_allow_html=True)

    rc_text = forensics.get("root_cause_hypothesis",
        "Azure Function 'eventhub_consumer' was auto-deployed to v2 at 02:11 UTC. "
        "v2 renamed merchant_name → merchant_nm and changed the date format from "
        "YYYY-MM-DD to DD-MM-YYYY. Snowflake COPY INTO ran on malformed JSON and "
        "silently loaded 0 rows. No alarm existed for zero-row loads."
    )
    st.markdown(f"""
    <div class="root-cause-box">
        <p>🔎 <strong>What broke:</strong> Azure Function v2 schema change</p>
        <p style="margin-top:0.6rem">⏱️ <strong>When:</strong> 02:11 UTC — 6 hours 52 min before detection</p>
        <p style="margin-top:0.6rem">🔇 <strong>Why silent:</strong> No alarm for zero-row Snowflake loads. Infrastructure appeared 100% healthy.</p>
        <p style="margin-top:0.8rem;font-size:0.78rem;color:#94a3b8">{rc_text}</p>
    </div>
    """, unsafe_allow_html=True)

    fa_text = recovery.get("status", "SUCCESS")
    st.markdown(f"""
    <div class="success-box" style="margin-top:0.8rem">
        <p>✅ <strong>Fix Applied ({fa_text})</strong></p>
        <p style="margin-top:0.5rem">⏪ Function rolled back to v1 in 8 seconds</p>
        <p style="margin-top:0.3rem">♻️ {records_recovered} records replayed from Event Hub with field mapping fix</p>
        <p style="margin-top:0.3rem">🚫 {records_quarantine} records quarantined (null transaction_ids)</p>
        <p style="margin-top:0.3rem">🔑 Idempotency key: transaction_id — 0 duplicates</p>
    </div>
    """, unsafe_allow_html=True)

with col_rec:
    st.markdown('<div class="section-title">♻️ Recovery Summary</div>', unsafe_allow_html=True)

    total  = records_missing
    pct_ok = records_recovered / total if total else 0
    pct_q  = records_quarantine / total if total else 0

    st.markdown(f"""
    <div style="margin-bottom:1rem">
        <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem">
            <span style="font-size:0.8rem;color:#94a3b8">Records Recovered</span>
            <span style="font-weight:700;color:#34d399">{records_recovered:,} / {total:,}</span>
        </div>
        <div class="rec-bar-wrap">
            <div class="rec-bar-fill" style="width:{pct_ok*100:.1f}%"></div>
        </div>
        <div style="font-size:0.7rem;color:#64748b;margin-top:0.2rem">{pct_ok*100:.1f}% of missing records restored</div>
    </div>
    <div style="margin-bottom:1.2rem">
        <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem">
            <span style="font-size:0.8rem;color:#94a3b8">Quarantined</span>
            <span style="font-weight:700;color:#a78bfa">{records_quarantine:,}</span>
        </div>
        <div class="rec-bar-wrap">
            <div class="rec-bar-fill" style="width:{pct_q*100:.1f}%;background:linear-gradient(90deg,#7c3aed,#a78bfa)"></div>
        </div>
        <div style="font-size:0.7rem;color:#64748b;margin-top:0.2rem">{pct_q*100:.1f}% quarantined — null PKs, cannot be replayed</div>
    </div>
    """, unsafe_allow_html=True)

    # Agent performance breakdown
    st.markdown('<div style="font-size:0.78rem;font-weight:600;color:#94a3b8;margin:0.8rem 0 0.4rem">Agent Performance Breakdown</div>', unsafe_allow_html=True)
    if agents_perf:
        max_dur = max(a["duration_sec"] for a in agents_perf) or 1
        for ap in agents_perf:
            name    = ap["agent"]
            dur     = ap["duration_sec"]
            bar_pct = dur / max_dur * 100
            col_a, col_b, col_c = st.columns([2, 4, 1])
            with col_a:
                st.markdown(f'<span style="font-size:0.78rem;color:#cbd5e1">{name}</span>', unsafe_allow_html=True)
            with col_b:
                st.markdown(f"""
                <div style="margin-top:0.4rem">
                  <div class="rec-bar-wrap">
                    <div class="rec-bar-fill" style="width:{bar_pct}%;background:linear-gradient(90deg,#6366f1,#8b5cf6)"></div>
                  </div>
                </div>""", unsafe_allow_html=True)
            with col_c:
                st.markdown(f'<span style="font-size:0.75rem;color:#94a3b8">{dur}s</span>', unsafe_allow_html=True)
    else:
        for name, dur in [("Forensics",4),("Impact",5),("Recovery",7),("Rollback",8),("Hardening",5),("IncidentReport",3)]:
            col_a, col_b, col_c = st.columns([2,4,1])
            with col_a:
                st.markdown(f'<span style="font-size:0.78rem;color:#cbd5e1">{name}</span>', unsafe_allow_html=True)
            with col_b:
                st.markdown(f"""
                <div style="margin-top:0.4rem">
                  <div class="rec-bar-wrap">
                    <div class="rec-bar-fill" style="width:{dur/8*100}%;background:linear-gradient(90deg,#6366f1,#8b5cf6)"></div>
                  </div>
                </div>""", unsafe_allow_html=True)
            with col_c:
                st.markdown(f'<span style="font-size:0.75rem;color:#94a3b8">{dur}s</span>', unsafe_allow_html=True)

    st.markdown(f"""
    <div style="margin-top:1rem;background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.25);border-radius:10px;padding:0.8rem 1rem">
      <div style="font-size:0.8rem;color:#a5b4fc;font-weight:600">💜 Total autonomous recovery time</div>
      <div style="font-size:1.8rem;font-weight:900;color:#c4b5fd">{recovery_time_sec}s</div>
      <div style="font-size:0.7rem;color:#64748b">Human interventions: 0 · Agents called: 6 · Tools used: 14</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — PREVENTION MEASURES (CloudWatch Alarms)
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-title">🛡️ Prevention — Hardening Agent Alarms</div>', unsafe_allow_html=True)

if data["alarms"]:
    alarm_cols = st.columns(len(data["alarms"]))
    for col, alarm in zip(alarm_cols, data["alarms"]):
        with col:
            alarm_chip(alarm["name"], alarm["trigger"], alarm["state"])
else:
    # Fallback to hardening data from JSON
    fallback_alarms = hardening.get("alarms_created", [])
    if fallback_alarms:
        alarm_cols = st.columns(len(fallback_alarms))
        descriptions = {
            "sigma-snowflake-zero-load":     "Fires if Snowflake ingestion loads zero rows for consecutive intervals.",
            "sigma-lambda-version-change":   "Fires when deployment-related Lambda failures spike suddenly.",
            "sigma-pipeline-row-divergence": "Fires when Event Hub events diverge significantly from Snowflake loaded rows.",
        }
        for col, alarm in zip(alarm_cols, fallback_alarms):
            with col:
                name = alarm.get("alert_name", "—")
                alarm_chip(name, descriptions.get(name, "—"), "INSUFFICIENT_DATA")
    else:
        st.info("No alarm data found — run create_azure_alert.py to create alarms.")

st.markdown("<hr/>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# QUARANTINE TABLE
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown(f'<div class="section-title">⚠️ Quarantined Records ({records_quarantine})</div>', unsafe_allow_html=True)

if not data["quarantine_df"].empty:
    df = data["quarantine_df"]
    # highlight quarantine metadata columns
    display_cols = [c for c in df.columns if not c.startswith("_")] + \
                   [c for c in df.columns if c.startswith("_")]
    st.dataframe(
        df[display_cols].style.set_properties(
            **{"background-color": "rgba(127,29,29,0.2)"},
            subset=[c for c in df.columns if c.startswith("_")]
        ),
        width="stretch",
        height=250,
    )
    st.caption(f"Source: {'Azure Blob quarantine/' if data['azure_source'] else 'local agent_outputs/'}")
else:
    st.info("No quarantine file found. Run generate_agent_outputs.py first.")

st.markdown("<hr/>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — FULL INCIDENT REPORT
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-title">📋 Full Incident Report — CTO Ready</div>', unsafe_allow_html=True)

if data["report_md"]:
    with st.expander(f"📄 {data['report_key']}  — click to expand", expanded=False):
        st.markdown(
            f'<div class="incident-report-box">{data["report_md"]}</div>',
            unsafe_allow_html=True
        )
else:
    st.warning(
        "No incident report found. "
        "Run `python lab/generate_agent_outputs.py` to generate one."
    )

# ═══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown(f"""
<div style="text-align:center;padding:1.5rem 0 0.5rem;color:#475569;font-size:0.72rem">
  ⚡ Sigma Intelligence Platform &nbsp;·&nbsp;
  7-Agent Self-Healing Pipeline &nbsp;·&nbsp;
  AWS Bedrock + Azure Event Hub + Snowflake &nbsp;·&nbsp;
  Day 12 &nbsp;·&nbsp;
  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
</div>
""", unsafe_allow_html=True)
