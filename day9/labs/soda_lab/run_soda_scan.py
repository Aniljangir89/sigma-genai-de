#!/usr/bin/env python3
"""
Soda Scan Runner - Execute Soda checks programmatically
"""
import sys
import json
from pathlib import Path
from soda.scan import Scan

def run_scan(table_name: str, output_file: str = None):
    """Run a Soda scan on the specified table"""
    
    # Initialize scan
    scan = Scan()
    scan.set_data_source_name("soda_duckdb")
    scan.set_scan_definition_name(f"Scan for {table_name}")
    
    # Load configuration
    with open("configuration.yml", "r") as f:
        config = f.read()
    scan.add_configuration_yaml_str(config)
    
    # Load checks
    with open("checks.yml", "r") as f:
        checks = f.read()
    
    # Replace table name in checks if needed
    checks = checks.replace("checks for day1_orders:", f"checks for {table_name}:")
    scan.add_sodacl_yaml_str(checks)
    
    # Execute scan
    scan.execute()
    
    # Print results
    print("\n" + "="*80)
    print(f"SODA SCAN RESULTS FOR {table_name}")
    print("="*80)
    print(scan.get_scan_result_as_json())
    
    # Save to file if requested
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(scan.get_scan_result_as_json())
        print(f"\n✓ Results saved to {output_file}")
    
    return scan

if __name__ == "__main__":
    table = sys.argv[1] if len(sys.argv) > 1 else "day1_orders"
    output = sys.argv[2] if len(sys.argv) > 2 else None
    
    run_scan(table, output)
