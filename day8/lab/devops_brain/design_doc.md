# Data Pipeline Design Document

## What This Pipeline Does
This pipeline ingests transaction data from both clean and dirty sources, processes it into a refined format, and aggregates it into merchant performance and daily summary metrics.

## Data Flow Diagram
```
+--------------------+      +--------------------+      +--------------------+      +--------------------+
|    Source          |      |     Bronze         |      |     Silver         |      |       Gold         |
|  (TRANSACTIONS)    |      | (bronze_transactions)|      | (silver_transactions)|      | (gold_merchant_performance, |
|                    |      |                     |      |                     |      |  gold_daily_summary)  |
+--------------------+      +--------------------+      +--------------------+      +--------------------+
     |                           |                           |                           |
     |                           |                           |                           |
     v                           v                           v                           v
+--------------------+      +--------------------+      +--------------------+      +--------------------+
| Load Merchants    |<----->| Load Bronze       |<----->| Transform Bronze   |      | Compute Metrics    |
| (merchants)        |       | (load_bronze)      |       | to Silver          |      | (compute_merchant_performance, |
|                    |       |                    |       | (transform_bronze_to_silver) |      |  compute_daily_summary) |
+--------------------+      +--------------------+      +--------------------+      +--------------------+
     |                           |                           |                           |
     |                           |                           |                           |
     v                           v                           v                           v
+--------------------+      +--------------------+      +--------------------+      +--------------------+
| Load Silver        |      | Load Gold          |      |                    |      |                    |
| (load_silver)      |      | (load_gold)        |      |                    |      |                    |
+--------------------+      +--------------------+      +--------------------+      +--------------------+
```

## Key Design Decisions
- **Layered Data Processing**: The pipeline uses a three-tier approach (Bronze, Silver, Gold) to ensure data quality and transformation are separated from raw data ingestion and final aggregation.
- **Quality Flags**: Introduced quality flags in the Silver layer to distinguish between clean and dirty transactions, allowing for more nuanced analysis.
- **Aggregation at Gold Layer**: Aggregations are performed at the Gold layer to provide high-level metrics and summaries, keeping the raw and transformed data separate.
- **Date-Partitioned Gold Tables**: The Gold layer tables are partitioned by date to facilitate time-series analysis and reporting.

## Known Limitations
- **Single Source of Merchants**: The pipeline assumes a static list of merchants. It does not handle dynamic updates to the merchant list.
- **Limited Error Handling**: The pipeline has basic error handling, primarily relying on `try-except` blocks which may not cover all edge cases.
- **No Data Validation**: The pipeline does not perform extensive data validation, relying on the assumption that the source data is mostly clean.
- **No Retry Mechanism**: The pipeline does not implement a retry mechanism for failed operations, which could lead to data loss in case of transient failures.

## Dependencies
- **DuckDB Database**: The pipeline requires a DuckDB database instance to store and process the data.
- **MERCHANTS Data**: A static list of merchants is required to enrich transaction data.
- **TRANSACTIONS_CLEAN and TRANSACTIONS_DIRTY**: The pipeline depends on these two data sources for raw transaction data.