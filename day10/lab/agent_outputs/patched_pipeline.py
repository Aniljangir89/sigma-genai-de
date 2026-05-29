# Patched by Self-Healing Agent — 2026-05-29T18:03:28.961974
# Attempts needed: 5

import duckdb, os

DB_PATH = r"/Users/as-mac-1336/Desktop/genAI/sigma-genai-de/day10/lab/sigma_platform.duckdb"

def run_merchant_report():
    conn = duckdb.connect(DB_PATH)
    df = conn.execute("SELECT * FROM silver_transactions WHERE amount > 0").fetchdf()
    if df.empty:
        print("No data found.")
        return
    total = df["amount"].sum()
    df2 = df.groupby("merchant_id").agg({"amount": "mean"}).reset_index()
    df2.columns = ["merchant_id", "avg_amount"]
    df2_sorted = df2.sort_values("avg_amount", ascending=False)
    print(f"Done. Total: {total:.2f}, Merchants: {len(df2)}")
    if not df2_sorted.empty:
        top = df2_sorted.iloc[0]["merchant_id"]
        print(f"Top merchant by avg amount: {top}")
    conn.close()

if __name__ == "__main__":
    run_merchant_report()