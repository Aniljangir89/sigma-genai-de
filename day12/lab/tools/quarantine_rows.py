
"""
==============================================================================
TOOL: quarantine_rows.py
==============================================================================
Purpose:
    Preserves failed records in quarantine storage.

Features:
    - Keeps bad records for human review
    - Adds quarantine metadata
    - Stores CSV snapshots

Storage:
    Primary   : Local filesystem  → lab/agent_outputs/
    Secondary : Azure Blob Storage (optional — skipped if not configured)

Used by:
    * Recovery Agent
    * Forensics Agent
    * Data Quality pipelines

==============================================================================
"""

import csv
import io
import json
import os
from pathlib import Path

from datetime import datetime, timezone
from dotenv import load_dotenv


load_dotenv()

# ── Local output directory (always written) ──────────────────────────────────
_HERE = Path(__file__).resolve().parent          # lab/tools/
_AGENT_OUTPUTS = _HERE.parent / "agent_outputs"  # lab/agent_outputs/
_AGENT_OUTPUTS.mkdir(parents=True, exist_ok=True)


# ── Main Entry ───────────────────────────────────────────────────────────────

def run_quarantine(
    records: list,
    quarantine_reason: str = "failed_quality_check",
    source_context: str = "eventhub_replay"
):

    return quarantine(
        records,
        quarantine_reason,
        source_context
    )


# ── Quarantine Logic ─────────────────────────────────────────────────────────

def quarantine(
    records: list,
    reason: str,
    source: str
) -> dict:

    if not records:

        return {
            "status": "SKIPPED",
            "reason": "no records to quarantine",
            "count": 0
        }

    # ── File Metadata ────────────────────────────────────────────────────

    ts = datetime.now(timezone.utc)
    fname = f"quarantine_{ts.strftime('%Y%m%d_%H%M%S')}.csv"

    # ── Annotate Records ────────────────────────────────────────────────────

    annotated = []
    for rec in records:
        row = dict(rec)
        row["_quarantine_reason"] = reason
        row["_quarantine_source"] = source
        row["_quarantined_at"]    = ts.isoformat()
        annotated.append(row)

    # ── Convert to CSV ────────────────────────────────────────────────────

    all_cols = list(annotated[0].keys())
    buf      = io.StringIO()
    writer   = csv.DictWriter(buf, fieldnames=all_cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(annotated)
    csv_bytes = buf.getvalue().encode("utf-8")

    # ── 1. Write to local agent_outputs/ (always) ──────────────────────────

    local_path = _AGENT_OUTPUTS / fname
    local_path.write_bytes(csv_bytes)
    print(f"  [quarantine_rows] Local: {local_path}")

    result = {
        "status":            "QUARANTINED",
        "record_count":      len(records),
        "local_path":        str(local_path),
        "quarantine_reason": reason,
        "quarantine_source": source,
        "quarantined_at":    ts.isoformat(),
        "note": (
            "Records preserved in agent_outputs/ and NOT loaded into Snowflake."
        ),
    }

    # ── 2. Also upload to Azure Blob Storage (optional) ─────────────────────

    storage_connection_string = os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    if storage_connection_string:
        try:
            from azure.storage.blob import BlobServiceClient
            blob_service_client = BlobServiceClient.from_connection_string(
                storage_connection_string
            )
            container_name = "quarantine"
            date           = ts.strftime("%Y-%m-%d")
            blob_path      = f"{date}/{fname}"
            blob_service_client.get_blob_client(
                container=container_name, blob=blob_path
            ).upload_blob(csv_bytes, overwrite=True)
            result["azure_blob_path"] = f"{container_name}/{blob_path}"
            print(f"  [quarantine_rows] Azure Blob: {container_name}/{blob_path}")
        except Exception as azure_err:
            print(f"  [quarantine_rows] Azure upload skipped: {azure_err}")

    return result


# ── Local Test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":

    test_records = [
        {
            "transaction_id": "",
            "merchant_name": "QuickMart",
            "amount": 500.0,
            "currency": "INR",
            "transaction_date": "2026-06-04",
        },
        {
            "transaction_id": "",
            "merchant_name": "FuelPlus",
            "amount": 200.0,
            "currency": "INR",
            "transaction_date": "2026-06-04",
        },
    ]

    result = run_quarantine(
        test_records,
        "null_transaction_id",
        "local_test"
    )

    print(json.dumps(result, indent=2))

