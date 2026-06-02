
"""
==============================================================================
Test MCP Tool Discovery
==============================================================================

Purpose:
    Tests Sigma MCP Server locally.

Checks:
    - Tool registry discovery
    - Tool availability
    - MCP health
    - Tool invocation

==============================================================================
"""

import sys
import os
import json 
sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            ".."
        )
    )
)

from sigma_mcp_server import (
    get_tools,
    health,
    invoke_tool,
)


EXPECTED_TOOLS = 9


print("\nSigma MCP Server — TOOL DISCOVERY TEST")
print("=" * 60)


# ── Health Check ────────────────────────────────────────────────────────────

print("\nChecking MCP health...\n")

health_result = health()

print(
    json.dumps(
        health_result,
        indent=2
    )
)

if health_result["status"] != "healthy":

    print("\n[FAIL] MCP server unhealthy")

    sys.exit(1)

print("\nHealth check: PASS")


# ── Tool Discovery ──────────────────────────────────────────────────────────

print("\nDiscovering tools...\n")

tool_result = get_tools()

tools = tool_result.get(
    "tools",
    []
)

print(
    f"Tools available to agents:\n"
)

for i, tool in enumerate(tools, 1):

    params = list(
        tool.get(
            "parameters",
            {}
        ).keys()
    )

    print(
        f"[{i}] {tool['name']}"
    )

    print(
        f"    {tool['description']}"
    )

    print(
        f"    Parameters: {params}\n"
    )

found = len(tools)

status = (
    "PASS"

    if found == EXPECTED_TOOLS

    else "FAIL"
)

print(
    f"{found}/{EXPECTED_TOOLS} "
    f"tools reachable."
)

print(
    f"MCP server status: {status}"
)

print("=" * 60)

if found != EXPECTED_TOOLS:

    print(
        f"\n[WARN] Expected "
        f"{EXPECTED_TOOLS} tools "
        f"but found {found}"
    )

    sys.exit(1)


# ── Sample Tool Invocation ──────────────────────────────────────────────────

print(
    "\nTesting sample MCP tool call...\n"
)

sample_result = invoke_tool(

    "create_azure_alert",

    {
        "alert_type":
            "eventhub_lag_spike"
    }
)

print(
    json.dumps(
        sample_result,
        indent=2
    )
)

if "result" in sample_result:

    print(
        "\nTool invocation test: PASS"
    )

else:

    print(
        "\nTool invocation test: FAIL"
    )

    sys.exit(1)


# ── Final Status ────────────────────────────────────────────────────────────

print(
    "\nAll MCP checks PASSED 🚀"
)

print(
    "\nSigma Autonomous AI Platform "
    "ready for agent orchestration.\n"
)
