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

revenue_by_merchant AS (
    SELECT
        ft.merchant_id,
        SUM(ft.amount) AS total_revenue
    FROM filtered_transactions ft
    WHERE ft.status = 'COMPLETED'
    GROUP BY ft.merchant_id
),

transaction_counts AS (
    SELECT
        merchant_id,
        COUNT(*) AS total_transactions,
        COUNT(CASE WHEN status = 'FAILED' THEN 1 END) AS failed_count
    FROM filtered_transactions
    GROUP BY merchant_id
),

avg_transaction_value AS (
    SELECT
        merchant_id,
        AVG(amount) AS avg_transaction_value
    FROM filtered_transactions
    WHERE status = 'COMPLETED'
    GROUP BY merchant_id
),

unique_customers AS (
    SELECT
        merchant_id,
        COUNT(DISTINCT customer_id) AS unique_customers
    FROM filtered_transactions
    GROUP BY merchant_id
)

SELECT
    md.merchant_id,
    md.merchant_name,
    md.category,
    md.city,
    md.onboarded_date,
    COALESCE(r.total_revenue, 0) AS total_revenue,
    COALESCE(tc.total_transactions, 0) AS total_transactions,
    COALESCE(tc.failed_count, 0) AS failed_count,
    COALESCE((tc.failed_count::DECIMAL / NULLIF(tc.total_transactions, 0)) * 100, 0) AS failure_rate_pct,
    COALESCE(av.avg_transaction_value, 0) AS avg_transaction_value,
    COALESCE(uc.unique_customers, 0) AS unique_customers
FROM merchant_details md
LEFT JOIN revenue_by_merchant r ON md.merchant_id = r.merchant_id
LEFT JOIN transaction_counts tc ON md.merchant_id = tc.merchant_id
LEFT JOIN avg_transaction_value av ON md.merchant_id = av.merchant_id
LEFT JOIN unique_customers uc ON md.merchant_id = uc.merchant_id
