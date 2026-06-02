"""
Day 12 Validator — The Sigma Intelligence Platform
Checks all required outputs exist and judgment questions are answered.

Architecture: Azure Event Hub → Blob Storage → Snowflake (NOT AWS S3)

Usage: python tests/validate_day12.py
"""

import boto3, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

ROOT       = Path(__file__).parent.parent
LAB_DIR    = ROOT / "lab"
OUTPUT_DIR = LAB_DIR / "agent_outputs"
CHAOS_LOG  = LAB_DIR / "chaos_log.md"

load_dotenv(LAB_DIR / ".env")

passed = 0
failed = 0
warns  = 0

def ok(msg):
    global passed; passed += 1
    print(f"  OK  {msg}")

def fail(msg):
    global failed; failed += 1
    print(f"  MISSING  {msg}")

def warn(msg):
    global warns; warns += 1
    print(f"  WARN  {msg}")

print()
print("=" * 55)
print("DAY 12 VALIDATOR — SIGMA INTELLIGENCE PLATFORM")
print("=" * 55)

# ── chaos_log.md ───────────────────────────────────────────────────────────────
print("\nPHASE 2 — CHAOS LOG:")
if CHAOS_LOG.exists():
    size    = CHAOS_LOG.stat().st_size
    content = CHAOS_LOG.read_text(encoding="utf-8")
    if size > 3000:
        ok(f"chaos_log.md  ({size:,} bytes — filled in)")
    else:
        fail(f"chaos_log.md  ({size:,} bytes — template not filled in, needs > 3KB)")
    if "___" in content:
        warn("chaos_log.md — blank fields still present (replace ___ with answers)")
else:
    fail("chaos_log.md  MISSING")

# ── Lambda tools deployed (AWS Lambda hosts all tool functions) ────────────────
print("\nPHASE 1 — LAMBDA TOOLS:")
region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
lam    = boto3.client("lambda", region_name=region)

tools = [
    "sigma-tool-check-azure-monitor",
    "sigma-tool-get-eventhub-records",
    "sigma-tool-query-snowflake",
    "sigma-tool-rollback-function",
    "sigma-tool-create-alert",
    "sigma-tool-quarantine-rows",
    "sigma-tool-load-snowflake",
    "sigma-tool-write-report",
    "sigma-tool-send-alert",
    "sigma-mcp-server",
]

for fn in tools:
    try:
        lam.get_function(FunctionName=fn)
        ok(fn)
    except Exception:
        fail(fn)

# ── Agent outputs — checks Azure Blob Storage, falls back to local ─────────────
print("\nPHASE 3 — AGENT OUTPUTS:")

azure_conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
today_str  = datetime.now(timezone.utc).strftime("%Y%m%d")

def _check_local_agent_outputs(container_prefix: str, pattern: str, label: str):
    """Check lab/agent_outputs/ for files matching pattern."""
    if OUTPUT_DIR.exists():
        matches = list(OUTPUT_DIR.glob(pattern))
        if matches:
            latest = sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)[0]
            ok(f"{label}  (local: agent_outputs/{latest.name})")
            return True
    fail(f"{label}  (not found — run pipeline_trigger.py then generate_agent_outputs.py)")
    return False

if azure_conn:
    try:
        from azure.storage.blob import BlobServiceClient
        blob_client = BlobServiceClient.from_connection_string(azure_conn)

        checks = [
            ("reports",    "incident_*.md",    "Incident report (Azure Blob reports/)"),
            ("quarantine", "quarantine_*.csv",  "Quarantine file (Azure Blob quarantine/)"),
        ]

        for container_name, local_pattern, label in checks:
            found_in_azure = False
            try:
                container = blob_client.get_container_client(container_name)
                blobs = list(container.list_blobs())
                # Accept any blob created today OR containing today's date string
                matching = [
                    b for b in blobs
                    if today_str in b.name
                    or (b.last_modified and b.last_modified.strftime("%Y%m%d") == today_str)
                ]
                if matching:
                    latest = sorted(matching, key=lambda b: b.last_modified, reverse=True)[0]
                    ok(f"{label}  ({latest.name})")
                    found_in_azure = True
                else:
                    # Accept ANY blob (not just today's) — tolerate date mismatch in training
                    if blobs:
                        latest = sorted(blobs, key=lambda b: b.last_modified, reverse=True)[0]
                        ok(f"{label}  ({latest.name})")
                        found_in_azure = True
            except Exception as e:
                pass  # fall through to local check

            if not found_in_azure:
                # Fallback: check local agent_outputs/
                _check_local_agent_outputs(container_name, local_pattern, label)

    except ImportError:
        warn("azure-storage-blob not installed — checking local agent_outputs/ instead")
        _check_local_agent_outputs("reports",    "incident_*.md",   "Incident report (local)")
        _check_local_agent_outputs("quarantine", "quarantine_*.csv","Quarantine file (local)")
else:
    # No Azure connection string — check local agent_outputs/
    warn("AZURE_STORAGE_CONNECTION_STRING not set — checking local agent_outputs/")
    _check_local_agent_outputs("reports",    "incident_*.md",   "Incident report (local agent_outputs/)")
    _check_local_agent_outputs("quarantine", "quarantine_*.csv","Quarantine file (local agent_outputs/)")

# ── CloudWatch alarms created by create_azure_alert.py ────────────────────────
print("\nPHASE 3 — CLOUDWATCH ALARMS:")

# create_azure_alert.py creates real CloudWatch alarms for validator compatibility.
# Check them in AWS CloudWatch first, then fall back to local alarms_created.json.

expected_alarms = [
    "sigma-snowflake-zero-load",
    "sigma-lambda-version-change",
    "sigma-pipeline-row-divergence",
]

# Try CloudWatch first
cw = boto3.client("cloudwatch", region_name=region)
alarms_local_path = OUTPUT_DIR / "alarms_created.json"

for alarm_name in expected_alarms:
    found = False
    try:
        resp   = cw.describe_alarms(AlarmNames=[alarm_name])
        alarms = resp.get("MetricAlarms", [])
        if alarms:
            state = alarms[0].get("StateValue", "?")
            ok(f"{alarm_name}  (CloudWatch state: {state})")
            found = True
    except Exception:
        pass  # AWS not reachable — fall through to local

    if not found:
        # Fallback: check local alarms_created.json
        if alarms_local_path.exists():
            try:
                data = json.loads(alarms_local_path.read_text(encoding="utf-8"))
                created = [a.get("alert_name", "") for a in data.get("alarms", [])]
                if alarm_name in created:
                    ok(f"{alarm_name}  (local alarms_created.json)")
                    found = True
            except Exception:
                pass

    if not found:
        fail(
            f"{alarm_name}  (not found in CloudWatch or agent_outputs/alarms_created.json — "
            f"run create_azure_alert.py or pipeline_trigger.py)"
        )

# ── Forensics extension ────────────────────────────────────────────────────────
print("\nPHASE 3 — FORENSICS EXTENSION:")
cw_tool = LAB_DIR / "tools" / "check_azure_monitor.py"
if cw_tool.exists():
    content = cw_tool.read_text(encoding="utf-8")
    new_code = any(
        kw in content for kw in [
            "Throttled", "zero-byte", "suspended", "Duration",
            "Iterator", "GetRecords.IteratorAgeMilliseconds"
        ]
    )
    if new_code:
        ok("check_azure_monitor.py — extension detected")
    else:
        fail("check_azure_monitor.py — no extension found (add Option A, B, or C from Phase 3)")
else:
    fail("check_azure_monitor.py — file missing")

# ── Judgment answers ───────────────────────────────────────────────────────────
print("\nJUDGMENT QUESTIONS:")
if CHAOS_LOG.exists():
    content = CHAOS_LOG.read_text(encoding="utf-8")
    questions = [
        ("Forensics Agent", "Forensics Agent:"),
        ("Recovery Agent",  "Recovery Agent:"),
        ("Hardening Agent", "Hardening Agent:"),
    ]
    for label, marker in questions:
        if marker in content:
            idx   = content.index(marker) + len(marker)
            after = content[idx:idx+500]
            answer_start = after.find("Your answer:")
            if answer_start >= 0:
                answer = after[answer_start+12:answer_start+200].strip()
                if answer and len(answer) > 20 and "___" not in answer:
                    ok(f"{label:40} answered")
                else:
                    fail(f"{label:40} NOT ANSWERED")

# ── Summary ────────────────────────────────────────────────────────────────────
print()
print("=" * 55)
total = passed + failed
if failed == 0 and warns == 0:
    print(f"  STATUS: ALL DONE — {passed}/{total} checks passed")
    print()
    print("  Push to your team fork:")
    print("    git add .")
    print('    git commit -m "Day 12 complete — self-healing agentic pipeline"')
    print("    git push")
elif failed == 0:
    print(f"  STATUS: COMPLETE WITH WARNINGS — {passed}/{total} passed, {warns} warnings")
    print("  Fix the warnings above before pushing.")
else:
    print(f"  STATUS: INCOMPLETE — {failed} item(s) missing")
    print(f"  Passed: {passed}/{total}")
    print("  Fix the missing items and re-run this validator.")
print("=" * 55)
print()

sys.exit(0 if failed == 0 else 1)
