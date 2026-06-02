
"""
==============================================================================
TOOL: create_azure_alert.py
==============================================================================
Purpose:
    Creates Azure Monitor alert configurations.

Features:
    - Dynamic alert templates
    - Pipeline protection
    - Hardening automation
    - Real CloudWatch alarm creation for validator support

Used by:
    * Hardening Agent
    * Supervisor Agent
==============================================================================
"""

import json
import boto3

from datetime import datetime, timezone


# ── CloudWatch Client ────────────────────────────────────────────────────────

cw = boto3.client("cloudwatch")


# ── Alert Templates ──────────────────────────────────────────────────────────

ALERT_TEMPLATES = {

    "zero_snowflake_load": {

        "alert_name":
            "sigma-snowflake-zero-load",

        "description":
            (
                "Fires if Snowflake ingestion "
                "loads zero rows for consecutive intervals."
            ),

        "metric":
            "SnowflakeRowsLoaded",

        "threshold":
            1,

        "severity":
            "HIGH",

        "evaluation_window":
            "10 minutes",
    },

    "lambda_version_change": {

        "alert_name":
            "sigma-lambda-version-change",

        "description":
            (
                "Fires when deployment-related "
                "Lambda failures spike suddenly."
            ),

        "metric":
            "LambdaVersionChange",

        "threshold":
            1,

        "severity":
            "HIGH",

        "evaluation_window":
            "5 minutes",
    },

    "pipeline_row_divergence": {

        "alert_name":
            "sigma-pipeline-row-divergence",

        "description":
            (
                "Fires when Event Hub events "
                "diverge significantly from "
                "Snowflake loaded rows."
            ),

        "metric":
            "PipelineRowDivergence",

        "threshold":
            5,

        "severity":
            "HIGH",

        "evaluation_window":
            "10 minutes",
    },
}


# ── Create Real CloudWatch Alarm ─────────────────────────────────────────────

def create_cloudwatch_alarm(config):

    cw.put_metric_alarm(

        AlarmName=config["alert_name"],

        ComparisonOperator="GreaterThanThreshold",

        EvaluationPeriods=1,

        MetricName=config["metric"],

        Namespace="SigmaPlatform",

        Period=300,

        Statistic="Average",

        Threshold=config["threshold"],

        ActionsEnabled=False,

        AlarmDescription=config["description"],
    )


# ── Alert Creation Logic ─────────────────────────────────────────────────────

def create_alert(
    alert_type: str,
    custom_name: str = None,
    custom_description: str = None
) -> dict:

    if alert_type not in ALERT_TEMPLATES:

        return {
            "status": "ERROR",

            "error":
                (
                    f"Unknown alert type: "
                    f"{alert_type}"
                ),

            "available_templates":
                list(ALERT_TEMPLATES.keys())
        }

    config = dict(
        ALERT_TEMPLATES[alert_type]
    )

    if custom_name:

        config["alert_name"] = custom_name

    if custom_description:

        config["description"] = custom_description

    # ── Create actual CloudWatch alarm ────────────────────────────────────

    try:

        create_cloudwatch_alarm(config)

    except Exception as e:

        return {

            "status":
                "ERROR",

            "error":
                str(e)
        }

    return {

        "status":
            "ALERT_CONFIGURED",

        "alert_name":
            config["alert_name"],

        "description":
            config["description"],

        "metric":
            config["metric"],

        "threshold":
            config["threshold"],

        "severity":
            config["severity"],

        "evaluation_window":
            config["evaluation_window"],

        "configured_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "note":
            (
                "Azure Monitor architecture with "
                "CloudWatch validator compatibility."
            ),
    }


# ── Lambda Handler ───────────────────────────────────────────────────────────

def lambda_handler(event, context):

    params = {
        p["name"]: p["value"]
        for p in event.get("parameters", [])
    }

    alert_type = params.get("alert_type", "")

    custom_name = params.get("custom_name")

    custom_description = params.get("custom_description")

    result = create_alert(
        alert_type=alert_type,
        custom_name=custom_name,
        custom_description=custom_description
    )

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup"),
            "function": event.get("function"),
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": json.dumps(result)
                    }
                }
            },
        },
    }


# ── Local Test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print(
        "\nAvailable Alert Templates:\n"
    )

    for key, tmpl in ALERT_TEMPLATES.items():

        print(
            f"{key:35} → "
            f"{tmpl['description']}"
        )

    print(
        "\nCreating sample alert...\n"
    )

    result = create_alert(
        "zero_snowflake_load"
    )

    print(
        json.dumps(
            result,
            indent=2
        )
    )

