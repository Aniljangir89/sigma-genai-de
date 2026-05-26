from typing import Dict, Any, List
from pyspark.sql import DataFrame
from pyspark.sql.types import StructType, StructField, StringType, FloatType, BooleanType, IntegerType

def detect_schema_drift(expected_schema: Dict[str, str], actual_schema: Dict[str, str]) -> Dict[str, Any]:
    new_columns = {k: v for k, v in actual_schema.items() if k not in expected_schema}
    removed_columns = {k: v for k, v in expected_schema.items() if k not in actual_schema}
    type_changes = {k: (expected_schema[k], actual_schema[k]) for k in expected_schema if expected_schema[k]!= actual_schema[k]}
    has_drift = bool(new_columns) or bool(removed_columns) or bool(type_changes)
    
    drift_severity = 'NONE'
    if removed_columns:
        drift_severity = 'BREAKING'
    elif any(v!= 'string' and v.endswith('Type') for v in new_columns.values()):
        drift_severity = 'HIGH'
    elif any('float' in v for v in new_columns.values()):
        drift_severity = 'HIGH'
    elif any('boolean' in v for v in new_columns.values()):
        drift_severity = 'LOW'
    
    return {
        "new_columns": new_columns,
        "removed_columns": removed_columns,
        "type_changes": type_changes,
        "has_drift": has_drift,
        "drift_severity": drift_severity
    }

def decide_action(drift_report: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    decisions = {}
    for column, data_type in drift_report["new_columns"].items():
        if data_type == "string":
            decisions[column] = {"action": "ADD_TO_SCHEMA", "reason": "New nullable string column", "risk_level": "LOW"}
        elif data_type in ["float", "double"]:
            decisions[column] = {"action": "FLAG_ANOMALY", "reason": "New float column affecting calculations", "risk_level": "HIGH"}
        elif data_type == "boolean":
            decisions[column] = {"action": "ADD_TO_SCHEMA", "reason": "New nullable boolean column", "risk_level": "LOW"}
    for column in drift_report["removed_columns"]:
        decisions[column] = {"action": "HALT", "reason": "Removed column will break downstream queries", "risk_level": "BREAKING"}
    return decisions

def apply_schema_evolution(spark_df: DataFrame, decisions: Dict[str, Dict[str, str]], updated_schema: Dict[str, str]) -> Tuple[DataFrame, List[str]]:
    migration_notes = []
    for column, decision in decisions.items():
        if decision["action"] == "DROP_SILENTLY":
            spark_df = spark_df.drop(column)
        elif decision["action"] == "ADD_TO_SCHEMA":
            migration_notes.append(f"Added column {column} to schema registry.")
        elif decision["action"] == "FLAG_ANOMALY":
            spark_df = spark_df.withColumn(f"{column}_anomaly", spark_df[column].isNull())
            migration_notes.append(f"Flagged anomalies for column {column}.")
    return spark_df, migration_notes

def handle_drift(expected_schema: Dict[str, str], actual_schema: Dict[str, str], spark_df: DataFrame = None) -> Dict[str, Any]:
    drift_report = detect_schema_drift(expected_schema, actual_schema)
    if not drift_report["has_drift"]:
        print("No schema drift detected.")
        return drift_report
    
    decisions = decide_action(drift_report)
    if spark_df is not None:
        evolved_df, migration_notes = apply_schema_evolution(spark_df, decisions, actual_schema)
        return {"drift_report": drift_report, "migration_notes": migration_notes}
    
    print("Schema drift detected:")
    print(f"New columns: {drift_report['new_columns']}")
    print(f"Removed columns: {drift_report['removed_columns']}")
    print(f"Type changes: {drift_report['type_changes']}")
    print(f"Drift severity: {drift_report['drift_severity']}")
    print("Action decisions:")
    for column, decision in decisions.items():
        print(f"{column}: {decision['action']} ({decision['reason']})")
    return {"drift_report": drift_report, "decisions": decisions}
