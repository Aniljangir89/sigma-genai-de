#!/usr/bin/env python3
"""
Direct Data Validation - Check data quality using DuckDB
"""
import duckdb
import json
from pathlib import Path
from datetime import datetime

def validate_day1_orders():
    """Validate day1_orders (clean data) - should all pass"""
    print("\n" + "="*80)
    print("VALIDATING DAY1_ORDERS (CLEAN DATA)")
    print("="*80)
    
    conn = duckdb.connect("soda_training.duckdb")
    results = {"timestamp": datetime.now().isoformat(), "checks": {}, "passed": 0, "failed": 0}
    
    # Check 1: Row count > 0
    row_count = conn.execute("SELECT COUNT(*) as cnt FROM day1_orders").fetchone()[0]
    passed = row_count > 0
    results["checks"]["row_count > 0"] = {"passed": passed, "value": row_count}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"✓ row_count > 0: {passed} (count={row_count})")
    
    # Check 2: No missing order_ids
    missing_ids = conn.execute("SELECT COUNT(*) FROM day1_orders WHERE order_id IS NULL").fetchone()[0]
    passed = missing_ids == 0
    results["checks"]["missing_count(order_id) = 0"] = {"passed": passed, "value": missing_ids}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"✓ missing_count(order_id) = 0: {passed} (missing={missing_ids})")
    
    # Check 3: No duplicate order_ids
    dups = conn.execute("SELECT COUNT(*) FROM (SELECT order_id, COUNT(*) as cnt FROM day1_orders GROUP BY order_id HAVING cnt > 1)").fetchone()[0]
    passed = dups == 0
    results["checks"]["duplicate_count(order_id) = 0"] = {"passed": passed, "value": dups}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"✓ duplicate_count(order_id) = 0: {passed} (duplicates={dups})")
    
    # Check 4: No missing customer_ids
    missing_cust = conn.execute("SELECT COUNT(*) FROM day1_orders WHERE customer_id IS NULL").fetchone()[0]
    passed = missing_cust == 0
    results["checks"]["missing_count(customer_id) = 0"] = {"passed": passed, "value": missing_cust}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"✓ missing_count(customer_id) = 0: {passed} (missing={missing_cust})")
    
    # Check 5: Amounts >= 0
    negative = conn.execute("SELECT COUNT(*) FROM day1_orders WHERE amount < 0").fetchone()[0]
    min_amt = conn.execute("SELECT MIN(amount) FROM day1_orders").fetchone()[0]
    passed = min_amt >= 0
    results["checks"]["min(amount) >= 0"] = {"passed": passed, "value": min_amt}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"✓ min(amount) >= 0: {passed} (min_amount={min_amt})")
    
    # Check 6: Valid status values
    valid_statuses = ['COMPLETED', 'PENDING', 'FAILED']
    invalid = conn.execute(f"SELECT COUNT(*) FROM day1_orders WHERE status NOT IN ({','.join([repr(s) for s in valid_statuses])})").fetchone()[0]
    passed = invalid == 0
    results["checks"]["invalid_count(status) = 0"] = {"passed": passed, "value": invalid}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"✓ invalid_count(status) = 0: {passed} (invalid={invalid})")
    
    conn.close()
    
    print(f"\n✓ PASSED: {results['passed']}/6")
    print(f"✗ FAILED: {results['failed']}/6\n")
    return results

def validate_day2_orders():
    """Validate day2_orders (dirty data) - should have failures"""
    print("\n" + "="*80)
    print("VALIDATING DAY2_ORDERS (DIRTY DATA)")
    print("="*80)
    
    conn = duckdb.connect("soda_training.duckdb")
    results = {"timestamp": datetime.now().isoformat(), "checks": {}, "passed": 0, "failed": 0}
    
    # Check 1: Row count > 0
    row_count = conn.execute("SELECT COUNT(*) as cnt FROM day2_orders").fetchone()[0]
    passed = row_count > 0
    results["checks"]["row_count > 0"] = {"passed": passed, "value": row_count}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"{'✓' if passed else '✗'} row_count > 0: {passed} (count={row_count})")
    
    # Check 2: No missing order_ids
    missing_ids = conn.execute("SELECT COUNT(*) FROM day2_orders WHERE order_id IS NULL").fetchone()[0]
    passed = missing_ids == 0
    results["checks"]["missing_count(order_id) = 0"] = {"passed": passed, "value": missing_ids}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"{'✓' if passed else '✗'} missing_count(order_id) = 0: {passed} (missing={missing_ids})")
    
    # Check 3: No duplicate order_ids
    dups = conn.execute("SELECT COUNT(*) FROM (SELECT order_id, COUNT(*) as cnt FROM day2_orders GROUP BY order_id HAVING cnt > 1)").fetchone()[0]
    passed = dups == 0
    results["checks"]["duplicate_count(order_id) = 0"] = {"passed": passed, "value": dups}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"{'✓' if passed else '✗'} duplicate_count(order_id) = 0: {passed} (duplicates={dups})")
    
    # Check 4: No missing customer_ids
    missing_cust = conn.execute("SELECT COUNT(*) FROM day2_orders WHERE customer_id IS NULL").fetchone()[0]
    passed = missing_cust == 0
    results["checks"]["missing_count(customer_id) = 0"] = {"passed": passed, "value": missing_cust}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"{'✓' if passed else '✗'} missing_count(customer_id) = 0: {passed} (missing={missing_cust})")
    
    # Check 5: Amounts >= 0
    negative = conn.execute("SELECT COUNT(*) FROM day2_orders WHERE amount < 0").fetchone()[0]
    min_amt = conn.execute("SELECT MIN(amount) FROM day2_orders").fetchone()[0]
    passed = min_amt >= 0
    results["checks"]["min(amount) >= 0"] = {"passed": passed, "value": min_amt}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"{'✓' if passed else '✗'} min(amount) >= 0: {passed} (min_amount={min_amt})")
    
    # Check 6: Valid status values
    valid_statuses = ['COMPLETED', 'PENDING', 'FAILED']
    invalid = conn.execute(f"SELECT COUNT(*) FROM day2_orders WHERE status NOT IN ({','.join([repr(s) for s in valid_statuses])})").fetchone()[0]
    passed = invalid == 0
    results["checks"]["invalid_count(status) = 0"] = {"passed": passed, "value": invalid}
    results["passed"] += 1 if passed else 0
    results["failed"] += 0 if passed else 1
    print(f"{'✓' if passed else '✗'} invalid_count(status) = 0: {passed} (invalid={invalid})")
    
    conn.close()
    
    print(f"\n✓ PASSED: {results['passed']}/6")
    print(f"✗ FAILED: {results['failed']}/6\n")
    return results

if __name__ == "__main__":
    day1 = validate_day1_orders()
    day2 = validate_day2_orders()
    
    # Display the data for inspection
    print("\n" + "="*80)
    print("DATA PREVIEW")
    print("="*80)
    
    conn = duckdb.connect("soda_training.duckdb")
    print("\nDAY1_ORDERS (Clean Data):")
    print(conn.execute("SELECT * FROM day1_orders").df())
    
    print("\nDAY2_ORDERS (Dirty Data):")
    print(conn.execute("SELECT * FROM day2_orders").df())
    conn.close()
