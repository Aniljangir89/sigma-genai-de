import logging
import shutil
from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import col, lit, max as max_, sum, count, avg, min, max, when, coalesce, to_date
from pyspark.sql.types import StringType, FloatType, DateType
import json
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)

def ingest_bronze(spark, input_path, output_path, run_date, run_id):
    try:
        logging.info("[Stage: Ingest Bronze] Starting ingestion")
        transactions_df = (spark.read.option("header", "true")
                          .option("inferSchema", "false")
                           .csv(input_path))

        transactions_df = (transactions_df.withColumn("ingestion_timestamp", lit(datetime.now().isoformat()))
                           .withColumn("source_file", lit("transactions.csv"))
                          .withColumn("pipeline_run_id", lit(run_id)))

        partition_path = f"{output_path}/{run_date}"
        shutil.rmtree(partition_path, ignore_errors=True)

        transactions_df.write.mode("overwrite").partitionBy("ingestion_timestamp").parquet(output_path)
        logging.info(f"[Stage: Ingest Bronze] Ingested {transactions_df.count():,} rows into {output_path}/{run_date}")
    except Exception as e:
        logging.error(f"[Stage: Ingest Bronze] Error: {e}, Row count: {transactions_df.count()}")
        raise

def transform_silver(spark, bronze_path, merchants_path, output_path, run_date):
    try:
        logging.info("[Stage: Transform Silver] Starting transformation")
        transactions_df = (spark.read.format("parquet")
                           .option("basePath", bronze_path)
                          .load(f"{bronze_path}/{run_date}"))

        transactions_df = (transactions_df.withColumn("amount", col("amount").cast(FloatType()))
                          .withColumn("transaction_date", col("transaction_date").cast(DateType()))
                          .withColumn("transaction_id", col("transaction_id").cast(StringType()))
                          .withColumn("merchant_id", col("merchant_id").cast(StringType())))

        input_count = transactions_df.count()
        logging.info(f"[Stage: Transform Silver] Input count: {input_count:,}")

        transactions_df = transactions_df.filter((col("transaction_id").isNotNull()) & (col("amount") >= 0))
        after_filter_count = transactions_df.count()
        logging.info(f"[Stage: Transform Silver] After filter count: {after_filter_count:,}")

        window = Window.partitionBy("transaction_id")
        transactions_df = (transactions_df.withColumn("rank", max_("ingestion_timestamp").over(window))
                           .filter(col("rank") == col("ingestion_timestamp"))
                          .drop("rank"))

        after_dedup_count = transactions_df.count()
        logging.info(f"[Stage: Transform Silver] After dedup count: {after_dedup_count:,}")

        merchants_df = (spark.read.option("header", "true")
                        .csv(merchants_path)
                        .withColumn("merchant_id", col("merchant_id").cast(StringType())))
        merchants_df = merchants_df.cache()

        enriched_df = (transactions_df.join(broadcast(merchants_df), "merchant_id", "left")
                       .withColumn("quality_flag",
                                   when(col("merchant_id").isNotNull(), "CLEAN").otherwise("UNMATCHED")))

        partition_path = f"{output_path}/{run_date}"
        shutil.rmtree(partition_path, ignore_errors=True)

        enriched_df.write.mode("overwrite").partitionBy("transaction_date").parquet(output_path)
        output_count = enriched_df.count()
        logging.info(f"[Stage: Transform Silver] Output count: {output_count:,}")
    except Exception as e:
        logging.error(f"[Stage: Transform Silver] Error: {e}, Row count: {transactions_df.count()}")
        raise

def run_gold(spark, silver_path, gold_output_dir, run_date):
    try:
        logging.info("[Stage: Run Gold] Starting gold layer processing")
        build_merchant_performance(spark, silver_path, f"{gold_output_dir}/merchant_performance", run_date)
        build_customer_ltv(spark, silver_path, f"{gold_output_dir}/customer_ltv")
        build_daily_summary(spark, silver_path, f"{gold_output_dir}/daily_summary", run_date)

        run_metadata = {
            "run_date": run_date,
            "status": "SUCCESS",
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat()
        }
        spark.range(1).write.json(f"{gold_output_dir}/run_metadata", mode="overwrite")
        logging.info("[Stage: Run Gold] Gold layer processing completed successfully")
    except Exception as e:
        logging.error(f"[Stage: Run Gold] Error: {e}")
        run_metadata = {
            "run_date": run_date,
            "status": "FAILED",
            "error_message": str(e),
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat()
        }
        spark.range(1).write.json(f"{gold_output_dir}/run_metadata", mode="overwrite")
        raise

def build_merchant_performance(spark, silver_path, output_path, run_date):
    try:
        logging.info("[Stage: Build Merchant Performance] Starting merchant performance calculation")
        silver_df = spark.read.parquet(silver_path).filter(col("transaction_date") == run_date)  # Partition pruning

        merchant_performance_df = silver_df.filter(col("status") == "COMPLETED") \
           .groupBy("merchant_id", "merchant_name", "category", "city", "transaction_date") \
           .agg(
                sum("amount").alias("total_revenue"),
                count("*").alias("txn_count"),
                (count(when(col("status") == "FAILED", 1)) / count("*") * 100).alias("failure_rate_pct")
            )

        partition_path = f"{output_path}/{run_date}"
        shutil.rmtree(partition_path, ignore_errors=True)

        merchant_performance_df.write.mode("overwrite").partitionBy("transaction_date").parquet(output_path)
        logging.info(f"[Stage: Build Merchant Performance] Wrote merchant performance to {output_path}/{run_date}")
    except Exception as e:
        logging.error(f"[Stage: Build Merchant Performance] Error: {e}")
        raise

def build_customer_ltv(spark, silver_path, output_path):
    try:
        logging.info("[Stage: Build Customer LTV] Starting customer LTV calculation")
        silver_df = spark.read.parquet(silver_path)

        customer_ltv_df = silver_df.filter(col("status") == "COMPLETED") \
           .groupBy("customer_id") \
           .agg(
                sum("amount").alias("total_spent"),
                count("*").alias("total_txns"),
                avg("amount").alias("avg_txn_value"),
                min("transaction_date").alias("first_txn_date"),
                max("transaction_date").alias("last_txn_date"),
                coalesce(max("payment_method").over(Window.partitionBy("customer_id")), lit(None)).alias("preferred_payment_method")
            )

        customer_ltv_df.write.mode("overwrite").parquet(output_path)
        logging.info(f"[Stage: Build Customer LTV] Wrote customer LTV to {output_path}")
    except Exception as e:
        logging.error(f"[Stage: Build Customer LTV] Error: {e}")
        raise

def build_daily_summary(spark, silver_path, output_path, run_date):
    try:
        logging.info("[Stage: Build Daily Summary] Starting daily summary calculation")
        silver_df = spark.read.parquet(silver_path).filter(col("transaction_date") == run_date)  # Partition pruning

        daily_summary_df = silver_df.groupBy("transaction_date") \
           .agg(
                sum(when(col("status") == "COMPLETED", col("amount")).otherwise(lit(0))).alias("total_revenue"),
                count("*").alias("total_txns"),
                count(distinct("customer_id")).alias("unique_customers"),
                count(distinct("merchant_id")).alias("unique_merchants"),
                (count(when(col("status") == "FAILED", 1)) / count("*") * 100).alias("failure_rate_pct")
            )

        partition_path = f"{output_path}/{run_date}"
        shutil.rmtree(partition_path, ignore_errors=True)

        daily_summary_df.write.mode("overwrite").partitionBy("transaction_date").parquet(output_path)
        logging.info(f"[Stage: Build Daily Summary] Wrote daily summary to {output_path}/{run_date}")
    except Exception as e:
        logging.error(f"[Stage: Build Daily Summary] Error: {e}")
        raise

def main():
    spark = (SparkSession.builder.appName("Sigma DataTech Transaction Analytics Pipeline")
             .getOrCreate())

    input_path = "s3://sigma-datatech-raw/transactions.csv"
    bronze_path = "s3://sigma-datatech-bronze/transactions"
    merchants_path = "s3://sigma-datatech-bronze/merchants"
    silver_path = "s3://sigma-datatech-silver/transactions"
    gold_output_dir = "s3://sigma-datatech-gold/transactions"
    run_date = datetime.now().strftime("%Y-%m-%d")
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")

    try:
        ingest_bronze(spark, input_path, f"{bronze_path}/{run_date}", run_date, run_id)
        transform_silver(spark, f"{bronze_path}/{run_date}", merchants_path, f"{silver_path}/{run_date}", run_date)
        run_gold(spark, f"{silver_path}/{run_date}", gold_output_dir, run_date)
    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        raise

if __name__ == "__main__":
    main()
