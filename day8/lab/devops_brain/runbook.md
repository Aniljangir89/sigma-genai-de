# Pipeline Overview

This pipeline ingests transaction data, transforms it into a cleaned and enriched format, and computes merchant performance and daily summary metrics. It runs to ensure data is up-to-date for downstream analytics and reporting. If it stops, critical business metrics and reports will be outdated.

## Pipeline Steps

1. Connect to DuckDB database using `get_connection()`.
2. Set up required tables using `setup_tables()`.
3. Load merchants data using `load_merchants()`.
4. Load raw transactions into the bronze table using `load_bronze()`.
5. Transform bronze transactions to silver using `transform_bronze_to_silver()`.
6. Load transformed transactions into the silver table using `load_silver()`.
7. Compute merchant performance metrics using `compute_merchant_performance()`.
8. Compute daily summary metrics using `compute_daily_summary()`.
9. Load computed metrics into gold tables using `load_gold()`.

## Schedule / Trigger

This pipeline runs every hour, triggered by a cron job.

## Failure Modes

1. **Database Connection Failure**
   - **Root Cause:** DuckDB service is down.
   - **Symptom:** `get_connection()` raises an exception.
2. **Table Creation Failure**
   - **Root Cause:** Syntax error in SQL.
   - **Symptom:** `setup_tables()` raises an exception.
3. **Merchant Data Load Failure**
   - **Root Cause:** Corrupted merchant data.
   - **Symptom:** `load_merchants()` raises an exception.
4. **Bronze Table Load Failure**
   - **Root Cause:** Malformed transaction data.
   - **Symptom:** `load_bronze()` raises an exception.
5. **Silver Table Transformation Failure**
   - **Root Cause:** Missing merchant mapping.
   - **Symptom:** `transform_bronze_to_silver()` raises an exception.

## Recovery Actions

1. **Database Connection Failure**
   - Check DuckDB service status.
   - Restart DuckDB service if down.
   - Retry pipeline.
2. **Table Creation Failure**
   - Review SQL syntax in `setup_tables()`.
   - Fix SQL errors.
   - Retry pipeline.
3. **Merchant Data Load Failure**
   - Validate merchant data integrity.
   - Correct any data issues.
   - Retry pipeline.
4. **Bronze Table Load Failure**
   - Inspect transaction data for errors.
   - Correct malformed records.
   - Retry pipeline.
5. **Silver Table Transformation Failure**
   - Ensure all merchants are mapped.
   - Add missing merchant mappings.
   - Retry pipeline.

## Known Bugs

- Hardcoded AWS credentials in the code.
- Lack of null handling in `transform_bronze_to_silver()`.

## Escalation Contacts

1. **On-call DE:** Priya Nair (priya.nair@sigmadatatech.in, +91-98400-11111)
2. **Tech Lead:** Arjun Mehta (arjun.mehta@sigmadatatech.in)
3. **Platform Manager:** Kavya Reddy (kavya.reddy@sigmadatatech.in)

## Data Quality Checks

- Verify the number of records in `silver_transactions` matches expected count.
- Check `gold_merchant_performance` for accurate merchant metrics.
- Ensure `gold_daily_summary` reflects current date's data.