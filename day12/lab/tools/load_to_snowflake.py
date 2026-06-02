
"""
==============================================================================
TOOL: load_to_snowflake.py
==============================================================================
Purpose:
    Loads clean transaction records into Snowflake.

Features:
    - MERGE INTO for idempotency
    - Safe replay support
    - Duplicate protection using transaction_id
    - Azure-compatible
    - Reusable by:
        * Azure Functions
        * MCP server
        * Bedrock agents
        * Recovery pipelines

==============================================================================
"""

import json
import os

from datetime import datetime, timezone
from dotenv import load_dotenv

import snowflake.connector


load_dotenv()


# ── Main Loader Entry ────────────────────────────────────────────────────────

def run_loader(records: list):

    table_name = (
        f"{os.getenv('SNOWFLAKE_DATABASE', 'SIGMA')}."
        f"{os.getenv('SNOWFLAKE_SCHEMA', 'SILVER')}."
        f"TRANSACTIONS"
    )

    return load(records, table_name)


# ── Snowflake Load Logic ─────────────────────────────────────────────────────

def load(records: list, table_name: str) -> dict:

    if not records:
        return {
            "status": "SKIPPED",
            "rows_loaded": 0,
            "rows_skipped": 0
        }

    # ── Connect to Snowflake ────────────────────────────────────────────────

    conn = snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        database=os.getenv("SNOWFLAKE_DATABASE", "SIGMA"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "SILVER"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    )

    cur = conn.cursor()

    ts = datetime.now(timezone.utc).isoformat()

    rows_loaded = 0
    rows_skipped = 0

    # ── Temporary Staging Table ─────────────────────────────────────────────

    cur.execute("""
        CREATE TEMPORARY TABLE IF NOT EXISTS temp_transactions (
            transaction_id   VARCHAR,
            merchant_name    VARCHAR,
            category         VARCHAR,
            amount           FLOAT,
            currency         VARCHAR,
            transaction_date DATE,
            status           VARCHAR,
            customer_id      VARCHAR,
            payment_method   VARCHAR,
            merchant_city    VARCHAR,
            _loaded_at       TIMESTAMP_TZ
        )
    """)

    # ── Prepare Batch ───────────────────────────────────────────────────────

    batch_values = []

    for rec in records:

        batch_values.append((
            rec.get("transaction_id", ""),
            rec.get("merchant_name", rec.get("merchant_nm", "")),
            rec.get("category", ""),
            float(rec.get("amount", 0) or 0),
            rec.get("currency", "INR"),
            rec.get("transaction_date", ""),
            rec.get("status", ""),
            rec.get("customer_id", ""),
            rec.get("payment_method", ""),
            rec.get("merchant_city", ""),
            ts,
        ))

    # ── Bulk Insert into Temp Table ─────────────────────────────────────────

    cur.executemany(
        """
        INSERT INTO temp_transactions
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        batch_values,
    )

    # ── MERGE INTO Main Table ───────────────────────────────────────────────

    cur.execute(f"""
        MERGE INTO {table_name} AS target
        USING temp_transactions AS src
        ON target.transaction_id = src.transaction_id

        WHEN NOT MATCHED THEN INSERT (
            transaction_id,
            merchant_name,
            category,
            amount,
            currency,
            transaction_date,
            status,
            customer_id,
            payment_method,
            merchant_city,
            _loaded_at
        )

        VALUES (
            src.transaction_id,
            src.merchant_name,
            src.category,
            src.amount,
            src.currency,
            src.transaction_date,
            src.status,
            src.customer_id,
            src.payment_method,
            src.merchant_city,
            src._loaded_at
        )
    """)

    # ── Metrics ─────────────────────────────────────────────────────────────

    cur.execute("SELECT COUNT(*) FROM temp_transactions")

    total = cur.fetchone()[0]

    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE _loaded_at = '{ts}'
        """
    )

    rows_loaded = cur.fetchone()[0]

    rows_skipped = total - rows_loaded

    # ── Commit + Cleanup ────────────────────────────────────────────────────

    conn.commit()

    cur.close()
    conn.close()

    return {
        "status": "LOADED",
        "table": table_name,
        "rows_attempted": len(records),
        "rows_loaded": rows_loaded,
        "rows_skipped": rows_skipped,
        "loaded_at": ts,
        "idempotency": (
            "MERGE ON transaction_id — safe replay enabled"
        ),
    }


# ── Local Test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":

    test_records = [
        {
            "transaction_id": "TXN-TEST-001",
            "merchant_name": "TestMart",
            "category": "retail",
            "amount": 100.0,
            "currency": "INR",
            "transaction_date": "2026-06-04",
            "status": "completed",
            "customer_id": "C9999",
            "payment_method": "UPI",
            "merchant_city": "Bengaluru",
        }
    ]

    print("\nLoading test records into Snowflake...\n")

    result = run_loader(test_records)

    print(json.dumps(result, indent=2))

    print("\nRunning idempotency replay test...\n")

    replay_result = run_loader(test_records)

    print(json.dumps(replay_result, indent=2))

