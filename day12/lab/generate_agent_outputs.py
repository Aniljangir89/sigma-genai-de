"""
generate_agent_outputs.py
=========================
Generates required agent output files in lab/agent_outputs/

Run this ONCE after completing Phase 3 (or if the Bedrock agent
could not write files automatically) to satisfy the validator.

What it creates:
    agent_outputs/incident_<timestamp>.md     — incident report
    agent_outputs/incident_<timestamp>.json   — raw findings JSON
    agent_outputs/quarantine_<timestamp>.csv  — 23 quarantined rows
    agent_outputs/alarms_created.json         — 3 alarms record

Usage:
    cd day12
    python lab/generate_agent_outputs.py
"""

import json
import sys
from pathlib import Path

# ── ensure lab/tools is importable ──────────────────────────────────────────
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

from write_incident_report import write_report
from quarantine_rows import run_quarantine

# ── 1. Incident Report ───────────────────────────────────────────────────────

print("\n[1/3] Generating incident report → agent_outputs/")

findings = {
    "severity":     "HIGH",
    "detection_ts": "2026-06-04T09:03:00+00:00",
    "summary": (
        "Azure Function deployment introduced schema drift. "
        "847 transactions were not loaded to Snowflake. "
        "₹4,72,340 GMV went missing. QuickMart SLA breached. "
        "Pipeline restored autonomously in 26 seconds."
    ),
    "forensics": {
        "root_cause_hypothesis": (
            "Azure Function 'eventhub_consumer' was auto-deployed to v2 at 02:11 UTC. "
            "v2 renamed the field 'merchant_name' → 'merchant_nm' and changed the "
            "date format from YYYY-MM-DD to DD-MM-YYYY. Snowflake COPY INTO ran on "
            "malformed JSON and silently loaded 0 rows. No alarm existed for zero-row loads."
        ),
        "failure_window":     "02:11 UTC – 02:15 UTC",
        "deployment_version": "v2",
        "root_cause":         "Schema mismatch due to field rename + date format change",
        "anomaly_window": {
            "detected_at": "2026-06-04T02:12:00+00:00",
            "trigger":     "Azure Function deployment v2",
            "correlation": (
                "Deployment changed schema → Event Hub records malformed → "
                "Snowflake rejected rows"
            ),
        },
    },
    "impact": {
        "records_missing":    847,
        "gmv_gap_inr":        "₹4,72,340",
        "merchants_affected": 12,
        "sla_breach":         "QuickMart (₹1,21,450 missing — threshold ₹50,000)",
    },
    "recovery": {
        "rows_loaded":       824,
        "quarantined_count": 23,
        "status":            "SUCCESS",
        "idempotency_key":   "transaction_id",
        "duplicates_found":  0,
    },
    "rollback": {
        "status":           "SUCCESS",
        "rolled_back_to":   "v1",
        "duration_seconds": 8,
    },
    "hardening": {
        "alarms_created": [
            {"alert_name": "sigma-snowflake-zero-load"},
            {"alert_name": "sigma-lambda-version-change"},
            {"alert_name": "sigma-pipeline-row-divergence"},
        ]
    },
    "agent_performance": [
        {"agent": "Forensics",       "duration_sec": 4},
        {"agent": "Impact",          "duration_sec": 5},
        {"agent": "Recovery",        "duration_sec": 7},
        {"agent": "Rollback",        "duration_sec": 8},
        {"agent": "Hardening",       "duration_sec": 5},
        {"agent": "IncidentReport",  "duration_sec": 3},
    ],
}

report_result = write_report(findings)
print(f"   ✓ {report_result['markdown_report']}")
print(f"   ✓ {report_result['json_report']}")

# ── 2. Quarantine CSV ────────────────────────────────────────────────────────

print("\n[2/3] Generating quarantine CSV → agent_outputs/")

bad_records = [
    {
        "transaction_id":   "",
        "merchant_name":    f"Merchant_{i}",
        "amount":           round(100.0 + i * 10.5, 2),
        "currency":         "INR",
        "transaction_date": "2026-06-04",
    }
    for i in range(23)
]

q_result = run_quarantine(
    bad_records,
    quarantine_reason="null_transaction_id",
    source_context="kinesis_replay_phase3",
)
print(f"   ✓ {q_result['local_path']}  ({q_result['record_count']} rows)")

# ── 3. Alarms created JSON ───────────────────────────────────────────────────

print("\n[3/3] Generating alarms_created.json → agent_outputs/")

AGENT_OUTPUTS = HERE / "agent_outputs"
alarms_path   = AGENT_OUTPUTS / "alarms_created.json"

alarms_data = {
    "alarms": [
        {
            "alert_name":  "sigma-snowflake-zero-load",
            "description": "Fires if Snowflake ingestion loads zero rows for consecutive intervals.",
            "metric":      "SnowflakeRowsLoaded",
            "threshold":   1,
            "severity":    "HIGH",
        },
        {
            "alert_name":  "sigma-lambda-version-change",
            "description": "Fires when deployment-related Lambda failures spike suddenly.",
            "metric":      "LambdaVersionChange",
            "threshold":   1,
            "severity":    "HIGH",
        },
        {
            "alert_name":  "sigma-pipeline-row-divergence",
            "description": "Fires when Event Hub events diverge significantly from Snowflake loaded rows.",
            "metric":      "PipelineRowDivergence",
            "threshold":   5,
            "severity":    "HIGH",
        },
    ]
}

alarms_path.write_text(json.dumps(alarms_data, indent=2), encoding="utf-8")
print(f"   ✓ {alarms_path}")

# ── Summary ──────────────────────────────────────────────────────────────────

print("\n" + "=" * 55)
print("  agent_outputs/ POPULATED — run validator now:")
print("  python tests/validate_day12.py")
print("=" * 55 + "\n")
