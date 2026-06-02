
"""
==============================================================================
DAY 13 — SIGMA DATATECH DATA GENERATOR
==============================================================================
Simulates Sigma DataTech's merchant transaction feed into Azure Event Hub.

Modes:
  --mode clean           → valid, well-formed records
  --mode chaos           → inject specific pain points (use --inject flag)

Inject options (use with --mode chaos):
  --inject schema_drift  → adds upi_ref_id, device_fingerprint; renames merchant_name → merchant_nm
  --inject pii_leak      → adds cust_ph, acct_no, emp_pncd in plain text
  --inject quality_rot   → null PKs, negative amounts, bad dates, unknown currencies
  --inject all           → all three combined

Usage:
  python data_generator.py --mode clean --records 200
  python data_generator.py --mode chaos --inject schema_drift --records 100
  python data_generator.py --mode chaos --inject all --records 500

==============================================================================
"""

import argparse
import json
import random
import time
import sys
import os

from datetime import datetime, timedelta
from dotenv import load_dotenv
from azure.eventhub import EventHubProducerClient, EventData

load_dotenv()

random.seed()

# ── Config ────────────────────────────────────────────────────────────────────
MERCHANTS = [
    "QuickMart", "FuelPlus", "CafeBlend", "TechZone", "MediPharm",
    "GroceryHub", "PetCorner", "AutoFix", "TravelEasy", "ByteStore"
]

CATEGORIES = [
    "retail", "fuel", "food", "electronics", "pharmacy",
    "grocery", "pet", "automotive", "travel", "tech"
]

CURRENCIES = [
    "INR", "INR", "INR", "INR", "INR",
    "INR", "USD", "EUR", "INR", "INR"
]

STATUSES = ["completed", "completed", "completed", "pending", "failed"]

CITIES = [
    "Bengaluru", "Mumbai", "Chennai",
    "Delhi", "Hyderabad", "Pune"
]

PAYMENTS = ["UPI", "card", "netbanking", "wallet"]

PHONES = [
    f"+91{random.randint(7000000000,9999999999)}"
    for _ in range(50)
]

ACCT_NOS = [
    f"{random.randint(100000000000,999999999999)}"
    for _ in range(50)
]

PIN_CODES = ["560001", "400001", "600001", "110001", "500001"]

UPI_REFS = [
    f"UPI-{random.randint(1000,9999)}-{random.randint(1000,9999)}"
    for _ in range(50)
]

DEVICE_FPS = [
    f"FP-{random.randint(100000,999999)}"
    for _ in range(50)
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def rand_date(days_back=7):
    d = datetime.now() - timedelta(days=random.randint(0, days_back))
    return d.strftime("%Y-%m-%d")


def make_clean_record(idx):
    m = random.randint(0, 9)

    return {
        "transaction_id": f"TXN{100000 + idx}",
        "merchant_name": MERCHANTS[m],
        "category": CATEGORIES[m],
        "amount": round(random.uniform(50, 25000), 2),
        "currency": CURRENCIES[m],
        "transaction_date": rand_date(),
        "status": random.choice(STATUSES),
        "customer_id": f"C{random.randint(1000,1099)}",
        "payment_method": random.choice(PAYMENTS),
        "merchant_city": random.choice(CITIES),
    }


def inject_schema_drift(record):
    """
    Rename merchant_name → merchant_nm
    Add extra columns.
    """
    record["merchant_nm"] = record.pop("merchant_name")
    record["upi_ref_id"] = random.choice(UPI_REFS)
    record["device_fingerprint"] = random.choice(DEVICE_FPS)

    return record


def inject_pii_leak(record):
    """
    Add PII columns.
    """
    record["cust_ph"] = random.choice(PHONES)
    record["acct_no"] = random.choice(ACCT_NOS)
    record["emp_pncd"] = random.choice(PIN_CODES)

    return record


def inject_quality_rot(record, idx, n_records):
    """
    Inject quality issues.
    """
    pct = idx / n_records

    if pct < 0.06:
        record["transaction_id"] = ""

    elif pct < 0.10:
        record["amount"] = -abs(record["amount"])

    elif pct < 0.125:
        record["transaction_date"] = "99-99-9999"

    elif pct < 0.14:
        record["currency"] = "XYZ"

    return record


# ── Azure Event Hub Sender ───────────────────────────────────────────────────

def send_to_eventhub(producer, record, verbose=True):
    """
    Send one record to Azure Event Hub.
    """

    try:
        data = json.dumps(record)

        batch = producer.create_batch()
        batch.add(EventData(data))

        producer.send_batch(batch)

        if verbose:
            tid = record.get("transaction_id") or "NULL"

            name = (
                record.get("merchant_name")
                or record.get("merchant_nm", "?")
            )

            amt = record.get("amount", 0)
            curr = record.get("currency", "?")

            print(
                f"  [OK] {str(tid):12} | "
                f"{name:12} | "
                f"{curr} {float(amt):>10,.2f}"
            )

        return True

    except Exception as e:
        print(f"[ERROR] Failed to send event: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():

    parser = argparse.ArgumentParser(
        description="Sigma DataTech Event Hub Data Generator"
    )

    parser.add_argument(
        "--mode",
        choices=["clean", "chaos"],
        default="clean"
    )

    parser.add_argument(
        "--inject",
        choices=["schema_drift", "pii_leak", "quality_rot", "all"],
        default=None
    )

    parser.add_argument(
        "--records",
        type=int,
        default=200
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Seconds between records"
    )

    args = parser.parse_args()

    if args.mode == "chaos" and args.inject is None:
        print("[ERROR] --mode chaos requires --inject flag")
        sys.exit(1)

    print("=" * 60)
    print("SIGMA DATATECH — EVENT HUB DATA GENERATOR")
    print("=" * 60)

    print(f"  Mode   : {args.mode.upper()}")

    if args.inject:
        print(f"  Inject : {args.inject.upper()}")

    print(f"  Records: {args.records}")

    print("=" * 60)

    # ── Azure Event Hub Connection ───────────────────────────────────────────

    try:
        producer = EventHubProducerClient.from_connection_string(
            conn_str=os.getenv("EVENT_HUB_CONNECTION_STRING"),
            eventhub_name=os.getenv("EVENT_HUB_NAME")
        )

    except Exception as e:
        print(f"[ERROR] Cannot connect to Azure Event Hub: {e}")
        sys.exit(1)

    sent = 0
    errors = 0

    start = time.time()

    # ── Generate Records ─────────────────────────────────────────────────────

    for i in range(args.records):

        record = make_clean_record(i)

        if args.mode == "chaos":

            inj = args.inject

            if inj in ("schema_drift", "all"):
                record = inject_schema_drift(record)

            if inj in ("pii_leak", "all"):
                record = inject_pii_leak(record)

            if inj in ("quality_rot", "all"):
                record = inject_quality_rot(
                    record,
                    i,
                    args.records
                )

        verbose = (i % 10 == 0)

        ok = send_to_eventhub(
            producer,
            record,
            verbose=verbose
        )

        if ok:
            sent += 1
        else:
            errors += 1

        time.sleep(args.delay)

    elapsed = round(time.time() - start, 1)

    # ── Summary ──────────────────────────────────────────────────────────────

    print("=" * 60)

    print(f"  DONE in {elapsed}s")
    print(f"  Sent  : {sent} records")
    print(f"  Errors: {errors} records")

    if args.mode == "chaos":

        print()

        if args.inject in ("schema_drift", "all"):
            print("  SCHEMA DRIFT injected:")
            print("    merchant_name → merchant_nm")
            print("    + upi_ref_id, device_fingerprint")

        if args.inject in ("pii_leak", "all"):
            print("  PII LEAK injected:")
            print("    + cust_ph, acct_no, emp_pncd")

        if args.inject in ("quality_rot", "all"):

            est_bad = round(args.records * 0.14)

            print("  QUALITY ROT injected:")
            print(f"    ~{round(args.records * 0.06)} null transaction_ids")
            print(f"    ~{round(args.records * 0.04)} negative amounts")
            print(f"    ~{round(args.records * 0.025)} bad dates")
            print(f"    ~{round(args.records * 0.015)} unknown currencies")
            print(f"    ~{est_bad} total bad records")

    print("=" * 60)
    print("  Events successfully published to Azure Event Hub.")
    print("=" * 60)


if __name__ == "__main__":
    main()

