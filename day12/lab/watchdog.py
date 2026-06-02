"""
╔══════════════════════════════════════════════════════════════════════════════╗
║             SIGMA INTELLIGENCE PLATFORM — AUTONOMOUS WATCHDOG               ║
║                   Real-Life End-to-End Automation                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  WHAT THIS DOES (Real-Life Production Pattern):                             ║
║                                                                              ║
║  Every 60 seconds this script does 3 checks:                                ║
║                                                                              ║
║  CHECK 1 — Azure Blob bronze/ vs Snowflake TRANSACTIONS                     ║
║    Counts files that landed in bronze/ in the last hour.                    ║
║    Counts rows loaded into Snowflake in the same window.                    ║
║    If gap > 5%  → pipeline is silently dropping records → fire agent.       ║
║                                                                              ║
║  CHECK 2 — GMV Drop (Business metric)                                       ║
║    Compares last-hour GMV to the 7-day average for the same hour.           ║
║    If GMV drops > 30% below baseline → something is wrong → fire agent.    ║
║                                                                              ║
║  CHECK 3 — Zero-row Snowflake load                                          ║
║    If Snowflake loaded 0 rows in the last 15 minutes → silent failure       ║
║    → fire agent immediately (most critical).                                 ║
║                                                                              ║
║  When ANY check fails → calls pipeline_trigger.py automatically             ║
║  → Bedrock supervisor agent runs → writes report to Azure Blob              ║
║  → Dashboard picks it up on next poll → 🆕 NEW DATA badge appears          ║
║                                                                              ║
║  REAL WORLD EQUIVALENT:                                                     ║
║  This is the same pattern as:                                               ║
║    • PhonePe's anomaly detection service                                    ║
║    • AWS CloudWatch Anomaly Detection + EventBridge + Lambda                ║
║    • Azure Monitor Alerts + Logic Apps + Function trigger                   ║
║    • Airflow SLA Miss callback → PagerDuty → runbook execution             ║
║                                                                              ║
║  Usage:                                                                      ║
║    cd day12                                                                  ║
║    python lab/watchdog.py                          # default: 60s interval  ║
║    python lab/watchdog.py --interval 30            # every 30 seconds       ║
║    python lab/watchdog.py --dry-run                # detect only, no agent  ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv

# ── Setup ─────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent          # lab/
ROOT = HERE.parent                              # day12/
load_dotenv(HERE / ".env")

AZURE_CONN   = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
REGION       = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# Thresholds — tune these for your pipeline volume
ROW_DIVERGENCE_PCT = 5      # Alert if Snowflake rows differ from blob files by >5%
GMV_DROP_PCT       = 30     # Alert if GMV drops >30% below 7-day baseline
ZERO_ROW_WINDOW    = 15     # Alert if 0 rows loaded in last N minutes

SEPARATOR = "─" * 72


# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

def log(level: str, msg: str):
    icons = {"INFO": "ℹ️ ", "OK": "✅", "WARN": "⚠️ ", "ALERT": "🚨", "AGENT": "🤖"}
    ts    = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {icons.get(level, '  ')} [{level:5}] {msg}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 1 — Azure Blob bronze/ file count vs Snowflake row count
# ═══════════════════════════════════════════════════════════════════════════════

def check_blob_vs_snowflake() -> dict:
    """
    Real-life check: compare how many files landed in bronze/
    against how many rows were loaded into Snowflake.
    If files exist but Snowflake rows are missing → silent failure.
    """
    result = {"check": "blob_vs_snowflake", "status": "ok", "details": {}}

    # — Azure Blob: count files in bronze/ from last hour —
    blob_files = 0
    if AZURE_CONN:
        try:
            from azure.storage.blob import BlobServiceClient
            blob_svc   = BlobServiceClient.from_connection_string(AZURE_CONN)
            container  = blob_svc.get_container_client("bronze")
            cutoff     = datetime.now(timezone.utc) - timedelta(hours=1)
            blob_files = sum(
                1 for b in container.list_blobs()
                if b.last_modified and b.last_modified > cutoff
            )
            result["details"]["blob_files_last_hour"] = blob_files
        except Exception as e:
            result["details"]["blob_error"] = str(e)

    # — Snowflake: count rows loaded in last hour —
    sf_rows = None
    try:
        sys.path.insert(0, str(HERE / "tools"))
        from query_snowflake import run_query
        cutoff_str = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        qr = run_query(
            f"SELECT COUNT(*) AS cnt FROM SIGMA.SILVER.TRANSACTIONS "
            f"WHERE _loaded_at >= '{cutoff_str}'",
            warehouse=None, max_rows=1
        )
        if "data" in qr and qr["data"]:
            sf_rows = qr["data"][0].get("cnt", 0)
            result["details"]["snowflake_rows_last_hour"] = sf_rows
    except Exception as e:
        result["details"]["snowflake_error"] = str(e)

    # — Compare —
    if blob_files > 0 and sf_rows is not None:
        # Rough estimate: each bronze file ≈ 100 records (adjust for your pipeline)
        expected_rows = blob_files * 100
        if expected_rows > 0:
            gap_pct = abs(expected_rows - sf_rows) / expected_rows * 100
            result["details"]["gap_pct"] = round(gap_pct, 1)
            if gap_pct > ROW_DIVERGENCE_PCT:
                result["status"]  = "alert"
                result["message"] = (
                    f"Row divergence {gap_pct:.1f}% — "
                    f"{blob_files} blob files, only {sf_rows} rows in Snowflake. "
                    f"Expected ~{expected_rows}. Pipeline is dropping records silently."
                )

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 2 — GMV drop vs 7-day baseline
# ═══════════════════════════════════════════════════════════════════════════════

def check_gmv_drop() -> dict:
    """
    Real-life check: compare current-hour GMV against the 7-day
    average for the same hour of day.
    A >30% drop means something is wrong — not just low traffic.
    """
    result = {"check": "gmv_drop", "status": "ok", "details": {}}
    try:
        sys.path.insert(0, str(HERE / "tools"))
        from query_snowflake import run_query

        now_hour = datetime.now(timezone.utc).hour

        # Current hour GMV
        qr_now = run_query(
            f"SELECT COALESCE(SUM(amount), 0) AS gmv "
            f"FROM SIGMA.SILVER.TRANSACTIONS "
            f"WHERE HOUR(transaction_date) = {now_hour} "
            f"AND DATE(transaction_date) = CURRENT_DATE()",
            warehouse=None, max_rows=1
        )
        gmv_now = 0
        if "data" in qr_now and qr_now["data"]:
            gmv_now = float(qr_now["data"][0].get("gmv", 0) or 0)

        # 7-day average for same hour
        qr_avg = run_query(
            f"SELECT COALESCE(AVG(daily_gmv), 0) AS avg_gmv FROM ("
            f"  SELECT DATE(transaction_date) AS d, SUM(amount) AS daily_gmv "
            f"  FROM SIGMA.SILVER.TRANSACTIONS "
            f"  WHERE HOUR(transaction_date) = {now_hour} "
            f"  AND transaction_date >= DATEADD(day, -7, CURRENT_DATE()) "
            f"  AND DATE(transaction_date) < CURRENT_DATE() "
            f"  GROUP BY 1"
            f")",
            warehouse=None, max_rows=1
        )
        gmv_avg = 0
        if "data" in qr_avg and qr_avg["data"]:
            gmv_avg = float(qr_avg["data"][0].get("avg_gmv", 0) or 0)

        result["details"]["gmv_current_hour"] = round(gmv_now, 2)
        result["details"]["gmv_7day_avg"]     = round(gmv_avg, 2)

        if gmv_avg > 0:
            drop_pct = (gmv_avg - gmv_now) / gmv_avg * 100
            result["details"]["drop_pct"] = round(drop_pct, 1)
            if drop_pct > GMV_DROP_PCT:
                result["status"]  = "alert"
                result["message"] = (
                    f"GMV drop {drop_pct:.1f}% below 7-day baseline — "
                    f"Current: ₹{gmv_now:,.0f} vs Average: ₹{gmv_avg:,.0f}. "
                    f"Possible silent pipeline failure."
                )

    except Exception as e:
        result["details"]["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 3 — Zero rows loaded in last N minutes
# ═══════════════════════════════════════════════════════════════════════════════

def check_zero_row_load() -> dict:
    """
    Real-life check: if Snowflake received ZERO rows in the last 15 minutes
    during business hours, the pipeline has a silent failure.
    This is the most critical check — catches issues the fastest.
    """
    result = {"check": "zero_row_load", "status": "ok", "details": {}}
    try:
        sys.path.insert(0, str(HERE / "tools"))
        from query_snowflake import run_query

        cutoff_str = (
            datetime.now(timezone.utc) - timedelta(minutes=ZERO_ROW_WINDOW)
        ).strftime("%Y-%m-%d %H:%M:%S")

        qr = run_query(
            f"SELECT COUNT(*) AS cnt FROM SIGMA.SILVER.TRANSACTIONS "
            f"WHERE _loaded_at >= '{cutoff_str}'",
            warehouse=None, max_rows=1
        )
        rows = 0
        if "data" in qr and qr["data"]:
            rows = int(qr["data"][0].get("cnt", 0) or 0)

        result["details"]["rows_last_15min"] = rows

        # Only alert during business hours (to avoid night-time noise)
        current_hour = datetime.now(timezone.utc).hour
        is_business_hours = 2 <= current_hour <= 22  # 7:30 AM–3:30 AM IST

        if rows == 0 and is_business_hours:
            result["status"]  = "alert"
            result["message"] = (
                f"ZERO rows loaded into Snowflake in the last {ZERO_ROW_WINDOW} minutes. "
                f"Pipeline is running but nothing is reaching the warehouse."
            )

    except Exception as e:
        result["details"]["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK 4 — Azure Blob zero-byte files (data arrives but is empty)
# ═══════════════════════════════════════════════════════════════════════════════

def check_zero_byte_blobs() -> dict:
    """
    Real-life check: files are landing in bronze/ but some have 0 bytes.
    This means the Event Hub consumer wrote empty files — a silent schema
    failure that looks healthy from the outside.
    """
    result = {"check": "zero_byte_blobs", "status": "ok", "details": {}}
    if not AZURE_CONN:
        return result
    try:
        from azure.storage.blob import BlobServiceClient
        blob_svc  = BlobServiceClient.from_connection_string(AZURE_CONN)
        container = blob_svc.get_container_client("bronze")
        cutoff    = datetime.now(timezone.utc) - timedelta(hours=1)

        zero_byte = [
            b.name for b in container.list_blobs()
            if b.last_modified and b.last_modified > cutoff and b.size == 0
        ]
        result["details"]["zero_byte_files"] = len(zero_byte)
        result["details"]["examples"]        = zero_byte[:3]

        if zero_byte:
            result["status"]  = "alert"
            result["message"] = (
                f"{len(zero_byte)} zero-byte files in blob bronze/ (last 1 hour). "
                f"Event Hub consumer is writing empty blobs — schema transform failure."
            )
    except Exception as e:
        result["details"]["error"] = str(e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# FIRE THE AGENT
# ═══════════════════════════════════════════════════════════════════════════════

def fire_agent(triggered_by: list[dict], dry_run: bool = False):
    """
    Calls pipeline_trigger.py with a message built from ALL failing checks.
    This is the same as a human typing the trigger command — but automatic.
    """
    # Build a descriptive message from all failing checks
    alert_lines = []
    for check in triggered_by:
        alert_lines.append(f"• {check.get('message', check['check'])}")

    message = (
        "AUTOMATED WATCHDOG ALERT — anomaly detected:\n\n"
        + "\n".join(alert_lines)
        + "\n\nPipeline appears healthy from infrastructure monitors "
        + "(Azure Functions running, Event Hub ingesting) but data is not "
        + "reaching Snowflake correctly.\n\n"
        + "Investigate root cause, recover missing records, prevent recurrence. "
        + "Generate a complete incident report."
    )

    trigger_script = HERE / "trigger" / "pipeline_trigger.py"

    log("AGENT", "Firing Bedrock Supervisor Agent...")
    log("AGENT", f"Triggered by: {[c['check'] for c in triggered_by]}")

    if dry_run:
        log("AGENT", "[DRY RUN] Would run:")
        log("AGENT", f"  python {trigger_script} --message \"...\"")
        log("AGENT", f"  Message:\n{message}")
        return

    try:
        result = subprocess.run(
            [sys.executable, str(trigger_script), "--message", message],
            cwd=str(ROOT),
            timeout=300,   # 5 minute timeout
            capture_output=False,
        )
        if result.returncode == 0:
            log("AGENT", "Agent completed successfully. Dashboard will update on next poll.")
        else:
            log("WARN",  f"Agent exited with code {result.returncode}")
    except subprocess.TimeoutExpired:
        log("WARN", "Agent timed out after 5 minutes — check pipeline_trigger.py")
    except Exception as e:
        log("WARN", f"Could not fire agent: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# COOLDOWN — avoid spamming the agent for the same incident
# ═══════════════════════════════════════════════════════════════════════════════

class Cooldown:
    """
    Prevents the watchdog from firing the agent repeatedly for the same
    ongoing incident. Real-life systems use a 30-minute cooldown.
    Once the agent runs, we wait 30 min before firing again.
    """
    def __init__(self, minutes: int = 30):
        self.minutes     = minutes
        self.last_fired  = None    # datetime of last agent run

    def can_fire(self) -> bool:
        if self.last_fired is None:
            return True
        elapsed = (datetime.now() - self.last_fired).total_seconds() / 60
        return elapsed >= self.minutes

    def mark_fired(self):
        self.last_fired = datetime.now()

    def next_allowed_in(self) -> str:
        if self.last_fired is None:
            return "now"
        elapsed  = (datetime.now() - self.last_fired).total_seconds() / 60
        wait_min = max(0, self.minutes - elapsed)
        return f"{wait_min:.0f} min"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def run_watchdog(interval: int = 60, dry_run: bool = False):
    cooldown = Cooldown(minutes=30)
    run_count = 0

    print()
    print("═" * 72)
    print("  SIGMA INTELLIGENCE PLATFORM — AUTONOMOUS WATCHDOG")
    print("═" * 72)
    print(f"  Check interval : every {interval} seconds")
    print(f"  Agent cooldown : 30 minutes between triggers")
    print(f"  Dry run        : {'YES — agent will NOT fire' if dry_run else 'NO — agent will fire on alert'}")
    print(f"  Data source    : {'Azure Blob Storage' if AZURE_CONN else 'LOCAL ONLY (no AZURE_CONN)'}")
    print("═" * 72)
    print()
    print("  THE FLOW:")
    print()
    print("  Azure Blob bronze/ ──┐")
    print("  Snowflake rows      ─┼──► Watchdog detects anomaly")
    print("  GMV metrics         ─┘          │")
    print("                               fire agent automatically")
    print("                                   │")
    print("                     Bedrock Supervisor Agent runs")
    print("                                   │")
    print("              Forensics │ Impact │ Recovery │ Hardening")
    print("                                   │")
    print("          writes  reports/ + quarantine/ to Azure Blob")
    print("                                   │")
    print("          Dashboard polls every 30s → 🆕 NEW DATA badge")
    print()
    print("  Press Ctrl+C to stop.")
    print(SEPARATOR)
    print()

    # ── Run checks immediately, then loop ────────────────────────────────────
    while True:
        run_count += 1
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{SEPARATOR}")
        print(f"  CHECK CYCLE #{run_count} — {ts}")
        print(SEPARATOR)

        # Run all 4 checks in sequence
        checks = []
        for fn, name in [
            (check_zero_row_load,    "Zero-row Snowflake load"),
            (check_zero_byte_blobs,  "Zero-byte Azure Blob files"),
            (check_blob_vs_snowflake,"Blob vs Snowflake row divergence"),
            (check_gmv_drop,         "GMV drop vs 7-day baseline"),
        ]:
            try:
                result = fn()
                checks.append(result)
                status  = result["status"]
                details = result.get("details", {})
                detail_str = " | ".join(f"{k}: {v}" for k, v in details.items()
                                        if k not in ("error",))

                if status == "ok":
                    log("OK",    f"{name} — {detail_str or 'healthy'}")
                elif status == "alert":
                    log("ALERT", f"{name} — {result.get('message', 'anomaly detected')}")
                else:
                    log("INFO",  f"{name} — {detail_str}")

            except Exception as e:
                log("WARN", f"{name} check failed: {e}")
                checks.append({"check": name, "status": "error", "details": {"error": str(e)}})

        # ── Decision: fire agent? ─────────────────────────────────────────────
        failing = [c for c in checks if c["status"] == "alert"]

        if failing:
            if cooldown.can_fire():
                print()
                log("ALERT", f"{'─'*55}")
                log("ALERT", f"{len(failing)} check(s) failed — firing agent automatically")
                log("ALERT", f"{'─'*55}")
                fire_agent(failing, dry_run=dry_run)
                if not dry_run:
                    cooldown.mark_fired()
            else:
                log("INFO",
                    f"{len(failing)} check(s) still failing — "
                    f"agent already fired, cooldown active "
                    f"(next allowed in {cooldown.next_allowed_in()})"
                )
        else:
            log("OK", "All checks passed — pipeline healthy ✓")

        # ── Sleep until next cycle ────────────────────────────────────────────
        print()
        log("INFO", f"Next check in {interval}s  |  Ctrl+C to stop")
        time.sleep(interval)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sigma Watchdog — autonomous pipeline anomaly detector"
    )
    parser.add_argument(
        "--interval", type=int, default=60,
        help="Check interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Detect anomalies but do NOT fire the agent"
    )
    args = parser.parse_args()

    try:
        run_watchdog(interval=args.interval, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n\n  Watchdog stopped.\n")
