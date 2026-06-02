
"""
==============================================================================
Sigma MCP Server
==============================================================================
Purpose:
    Exposes all Sigma platform tools as discoverable MCP-style resources.

Architecture:
    Bedrock Agent
        ↓
    MCP Server
        ↓
    Python Tool Registry
        ↓
    Azure + Snowflake Platform Tools

==============================================================================    
"""

import sys
import os

sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            ".."
        )
    )
)

import json

from datetime import datetime, timezone


# ── Tool Imports ────────────────────────────────────────────────────────────

from tools.check_azure_monitor import investigate

from tools.get_eventhub_records import replay_records

from tools.query_snowflake import run_query

from tools.rollback_function_deployment import rollback

from tools.create_azure_alert import create_alert

from tools.quarantine_rows import run_quarantine

from tools.load_to_snowflake import run_loader

from tools.write_incident_report import write_report

from tools.send_teams_alert import send_alert


# ── Tool Registry ───────────────────────────────────────────────────────────

TOOLS = [

    {
        "name":
            "check_azure_monitor",

        "description":
            (
                "Investigates Azure platform failures, "
                "deployment anomalies, Event Hub issues, "
                "and Snowflake ingestion failures."
            ),

        "parameters": {

            "function_name": {

                "type":
                    "string",

                "required":
                    False,

                "default":
                    "eventhub_consumer"
            },

            "hours_back": {

                "type":
                    "integer",

                "required":
                    False,

                "default":
                    8
            }
        }
    },

    {
        "name":
            "get_eventhub_records",

        "description":
            (
                "Replays Event Hub records and "
                "applies schema repair logic."
            ),

        "parameters": {

            "already_loaded_ids": {

                "type":
                    "array",

                "required":
                    False
            },

            "max_events": {

                "type":
                    "integer",

                "required":
                    False,

                "default":
                    100
            }
        }
    },

    {
        "name":
            "query_snowflake",

        "description":
            (
                "Executes SQL queries against Snowflake."
            ),

        "parameters": {

            "sql": {

                "type":
                    "string",

                "required":
                    True
            }
        }
    },

    {
        "name":
            "rollback_function_deployment",

        "description":
            (
                "Rolls back Azure Function deployment "
                "after failed release."
            ),

        "parameters": {

            "function_name": {

                "type":
                    "string",

                "required":
                    False,

                "default":
                    "eventhub_consumer"
            }
        }
    },

    {
        "name":
            "create_azure_alert",

        "description":
            (
                "Creates Azure Monitor alert definitions."
            ),

        "parameters": {

            "alert_type": {

                "type":
                    "string",

                "required":
                    True
            }
        }
    },

    {
        "name":
            "quarantine_rows",

        "description":
            (
                "Moves invalid records into "
                "quarantine Blob container."
            ),

        "parameters": {

            "records": {

                "type":
                    "array",

                "required":
                    True
            },

            "quarantine_reason": {

                "type":
                    "string",

                "required":
                    True
            }
        }
    },

    {
        "name":
            "load_to_snowflake",

        "description":
            (
                "Loads clean records into Snowflake "
                "using replay-safe MERGE."
            ),

        "parameters": {

            "records": {

                "type":
                    "array",

                "required":
                    True
            }
        }
    },

    {
        "name":
            "write_incident_report",

        "description":
            (
                "Generates executive incident reports."
            ),

        "parameters": {

            "findings": {

                "type":
                    "object",

                "required":
                    True
            }
        }
    },

    {
        "name":
            "send_teams_alert",

        "description":
            (
                "Sends Teams incident notifications."
            ),

        "parameters": {

            "message": {

                "type":
                    "string",

                "required":
                    True
            },

            "severity": {

                "type":
                    "string",

                "required":
                    False,

                "default":
                    "high"
            }
        }
    }
]


# ── Tool Function Mapping ───────────────────────────────────────────────────

TOOL_FUNCTIONS = {

    "check_azure_monitor":
        investigate,

    "get_eventhub_records":
        replay_records,

    "query_snowflake":
        run_query,

    "rollback_function_deployment":
        rollback,

    "create_azure_alert":
        create_alert,

    "quarantine_rows":
        run_quarantine,

    "load_to_snowflake":
        run_loader,

    "write_incident_report":
        write_report,

    "send_teams_alert":
        send_alert,
}


# ── MCP Tool Invocation ─────────────────────────────────────────────────────

def invoke_tool(
    tool_name: str,
    params: dict
):

    tool_fn = TOOL_FUNCTIONS.get(
        tool_name
    )

    if not tool_fn:

        return {

            "tool":
                tool_name,

            "error":
                "Tool not found"
        }

    try:

        result = tool_fn(**params)

        return {

            "tool":
                tool_name,

            "result":
                result
        }

    except Exception as e:

        return {

            "tool":
                tool_name,

            "error":
                str(e)
        }


# ── MCP Discovery API ───────────────────────────────────────────────────────

def get_tools():

    return {

        "tools":
            TOOLS,

        "count":
            len(TOOLS),

        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "description":
            (
                "Sigma Autonomous AI Platform "
                "Tool Registry"
            )
    }


# ── Health Check ────────────────────────────────────────────────────────────

def health():

    return {

        "status":
            "healthy",

        "tools_available":
            len(TOOLS),

        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }


# ── Local Test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print(
        "\nSigma MCP Server\n"
    )

    print(
        json.dumps(
            get_tools(),
            indent=2
        )
    )

    print(
        "\nHealth Check:\n"
    )

    print(
        json.dumps(
            health(),
            indent=2
        )
    )

    print(
        "\nSample Tool Invocation:\n"
    )

    result = invoke_tool(

        "create_azure_alert",

        {
            "alert_type":
                "eventhub_lag_spike"
        }
    )

    print(
        json.dumps(
            result,
            indent=2
        )
    )
