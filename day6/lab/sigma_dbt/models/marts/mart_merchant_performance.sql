WITH filtered_transactions AS (
    SELECT
        transaction_id,
        amount,
        status,
        merchant_id,
        customer_id,
        transaction_date,
        payment_method
    FROM {{ ref('stg_fact_transactions') }}
    WHERE status IN ('COMPLETED', 'FAILED')
),

merchant_details AS (
    SELECT
        merchant_id,
        merchant_name,
        category,
        city,
        onboarded_date
    FROM {{ ref('dim_merchant') }}
),

aggregated_metrics AS (
    SELECT
        ft.merchant_id,
        COUNT(ft.transaction_id) AS total_transactions,
        COUNT(CASE WHEN ft.status = 'FAILED' THEN 1 END) AS failed_count,
        SUM(CASE WHEN ft.status = 'COMPLETED' THEN ft.amount ELSE 0 END) AS total_revenue,
        AVG(CASE WHEN ft.status = 'COMPLETED' THEN ft.amount ELSE NULL END) AS avg_transaction_value,
        COUNT(DISTINCT ft.customer_id) AS unique_customers
    FROM filtered_transactions ft
    GROUP BY ft.merchant_id
)

SELECT
    md.merchant_id,
    md.merchant_name,
    md.category,
    md.city,
    md.onboarded_date,
    am.total_transactions,
    am.failed_count,
    am.total_revenue,
    am.avg_transaction_value,
    am.unique_customers,
    (am.failed_count::FLOAT / am.total_transactions) * 100 AS failure_rate_pct
FROM aggregated_metrics am
JOIN merchant_details md ON am.merchant_id = md.merchant_id
```

```yaml
version: 2

models:
  - name: mart_merchant_kpis
    description: "Aggregated merchant KPIs including total revenue, total transactions, failed count, failure rate, average transaction value, and unique customers."
    columns:
      - name: merchant_id
        description: "Unique identifier for the merchant."
        tests:
          - not_null
          - unique
          - relationships:
              to: ref('dim_merchant')
              field: merchant_id
      - name: merchant_name
        description: "Name of the merchant."
        tests:
          - not_null
      - name: category
        description: "Category of the merchant."
        tests:
          - not_null
          - accepted_values:
              values: ["Food Delivery", "E-Commerce", "Entertainment", "Travel", "Grocery"]
      - name: city
        description: "City where the merchant is located."
        tests:
          - not_null
      - name: onboarded_date
        description: "Date when the merchant was onboarded."
        tests:
          - not_null
      - name: total_transactions
        description: "Total number of transactions for the merchant."
        tests:
          - not_null
      - name: failed_count
        description: "Number of failed transactions for the merchant."
        tests:
          - not_null
      - name: total_revenue
        description: "Total revenue from completed transactions for the merchant."
        tests:
          - not_null
      - name: avg_transaction_value
        description: "Average value of completed transactions for the merchant."
        tests:
          - not_null
      - name: unique_customers
        description: "Number of unique customers who made transactions with the merchant."
        tests:
          - not_null
      - name: failure_rate_pct
        description: "Failure rate percentage of transactions for the merchant."
