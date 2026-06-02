
"""
==============================================================================
TOOL: get_eventhub_records.py
==============================================================================
Purpose:
    Replays records from Azure Event Hub.

Features:
    - Replay-safe recovery
    - Duplicate prevention
    - Field repair logic
    - Used by:
        * Recovery Agent
        * Forensics Agent
        * Replay pipelines

==============================================================================
"""

import json
import os
import re

from dotenv import load_dotenv

from azure.eventhub import EventHubConsumerClient


load_dotenv()


# ── Record Repair Logic ──────────────────────────────────────────────────────

def fix_record(record: dict) -> dict:

    fixed = dict(record)

    # merchant_nm → merchant_name
    if "merchant_nm" in fixed and "merchant_name" not in fixed:

        fixed["merchant_name"] = fixed.pop(
            "merchant_nm"
        )

    # DD-MM-YYYY → YYYY-MM-DD
    date_val = fixed.get("transaction_date", "")

    if re.match(r"^\d{2}-\d{2}-\d{4}$", str(date_val)):

        parts = str(date_val).split("-")

        fixed["transaction_date"] = (
            f"{parts[2]}-{parts[1]}-{parts[0]}"
        )

    return fixed


# ── Replay Logic ─────────────────────────────────────────────────────────────

def replay_records(
    already_loaded_ids: list = [],
    max_events: int = 100
):

    connection_str = os.getenv(
        "EVENT_HUB_CONNECTION_STRING"
    )

    eventhub_name = os.getenv(
        "EVENT_HUB_NAME",
        "sigma-transactions"
    )

    consumer_group = "$Default"

    loaded_set = set(already_loaded_ids)

    raw_records = []

    fixed_records = []

    skipped_ids = []

    # ── Event Processing ────────────────────────────────────────────────────

    def on_event(partition_context, event):

        nonlocal raw_records
        nonlocal fixed_records
        nonlocal skipped_ids

        try:

            data = json.loads(
                event.body_as_str()
            )

            raw_records.append(data)

            fixed = fix_record(data)

            tid = fixed.get(
                "transaction_id",
                ""
            )

            if tid and tid in loaded_set:

                skipped_ids.append(tid)

            else:

                fixed_records.append(fixed)

                if tid:
                    loaded_set.add(tid)

        except Exception:

            pass

    # ── Create Event Hub Consumer ──────────────────────────────────────────

    client = EventHubConsumerClient.from_connection_string(
        conn_str=connection_str,
        consumer_group=consumer_group,
        eventhub_name=eventhub_name,
    )

    # ── Receive Replay Events ──────────────────────────────────────────────

    with client:

        client.receive(
            on_event=on_event,
            starting_position="-1",  # earliest events
            max_wait_time=5
        )

    return {
        "eventhub_name": eventhub_name,
        "raw_records_found": len(raw_records),
        "duplicates_skipped": len(skipped_ids),
        "clean_records": len(fixed_records),
        "records": fixed_records,
        "field_fixes_applied": {
            "merchant_nm_renamed": sum(
                1 for r in raw_records
                if "merchant_nm" in r
            ),
            "date_format_fixed": sum(
                1 for r in raw_records
                if re.match(
                    r"^\d{2}-\d{2}-\d{4}$",
                    str(r.get("transaction_date", ""))
                )
            ),
        },
    }


# ── Local Test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print(
        "\nReplaying Event Hub records...\n"
    )

    result = replay_records()

    print(
        f"Raw records found  : "
        f"{result['raw_records_found']}"
    )

    print(
        f"Duplicates skipped : "
        f"{result['duplicates_skipped']}"
    )

    print(
        f"Clean records      : "
        f"{result['clean_records']}"
    )

    print(
        f"Field fixes        : "
        f"{result['field_fixes_applied']}"
    )

    if result["records"]:

        print(
            "\nSample record:\n"
        )

        print(
            json.dumps(
                result["records"][0],
                indent=2
            )
        )

