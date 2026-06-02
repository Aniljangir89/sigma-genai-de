
"""
Pipeline Trigger — run from your laptop.

Invokes the Bedrock Supervisor Agent
and streams orchestration reasoning live.

Usage:

python trigger/pipeline_trigger.py

python trigger/pipeline_trigger.py --health-check

python trigger/pipeline_trigger.py --mode clean

python trigger/pipeline_trigger.py \
  --message "GMV dropped suddenly. Investigate and recover."
"""

import argparse
import boto3
import json
import os
import sys
import time

from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# ── Optional Langfuse Observability ──────────────────────────────────────────

try:

    from langfuse import Langfuse as _Langfuse

    _lf = (
        _Langfuse()
        if os.getenv("LANGFUSE_PUBLIC_KEY")
        else None
    )

except ImportError:

    _lf = None


# ── Environment ──────────────────────────────────────────────────────────────

REGION = os.getenv(
    "AWS_DEFAULT_REGION",
    "us-east-1"
)

SUPERVISOR_ID = os.getenv(
    "SUPERVISOR_AGENT_ID",
    ""
)

SUPERVISOR_ALIAS = os.getenv(
    "SUPERVISOR_ALIAS_ID",
    "TSTALIASID"
)

DEFAULT_CONTAINER = os.getenv(
    "AZURE_STORAGE_CONTAINER",
    "reports"
)


# ── Incident Messages ────────────────────────────────────────────────────────

INCIDENT_MESSAGE = (
    "Dashboard shows 40,000 transactions today "
    "but historical baseline is 1,20,000. "
    "80,000 records appear missing.\n\n"

    "Azure Functions show healthy execution.\n"
    "Event Hub shows successful ingestion.\n"
    "Blob Storage contains ingestion files.\n"
    "However Snowflake row counts remain far below "
    "expected ingestion volume since 02:00 UTC.\n\n"

    "Investigate the root cause.\n"
    "Recover missing records safely.\n"
    "Prevent recurrence.\n"
    "Generate a complete incident report."
)

CLEAN_MESSAGE = (
    "Run a full health check on the platform.\n"
    "Confirm clean data flow from Event Hub "
    "to Snowflake.\n"
    "Report row counts, replay status, "
    "and GMV for the last hour."
)


# ── Health Check ─────────────────────────────────────────────────────────────

def health_check():

    lam = boto3.client(
        "lambda",
        region_name=REGION
    )

   
  
    tools = [

        "sigma-tool-check-azure-monitor",

        "sigma-tool-get-eventhub-records",

        "sigma-tool-query-snowflake",

        "sigma-tool-rollback-function",

        "sigma-tool-create-alert",

        "sigma-tool-quarantine-rows",

        "sigma-tool-load-snowflake",

        "sigma-tool-write-report",

        "sigma-tool-send-alert",

        "sigma-mcp-server",
    ]




    print(
        "\nHEALTH CHECK — AI TOOLING"
    )

    print("=" * 60)

    all_ok = True

    for fn in tools:

        try:

            lam.get_function(
                FunctionName=fn
            )

            print(f"  OK  {fn}")

        except Exception:

            print(f"  MISSING  {fn}")

            all_ok = False

    print("=" * 60)

    if not SUPERVISOR_ID:

        print(
            "  WARN  SUPERVISOR_AGENT_ID "
            "not set in .env"
        )

        all_ok = False

    else:

        print(
            f"  OK  Supervisor Agent ID: "
            f"{SUPERVISOR_ID}"
        )

    print(
        f"\n"
        f"{'ALL TOOLS READY' if all_ok else 'SOME TOOLS MISSING'}"
    )

    return all_ok


# ── Supervisor Invocation ────────────────────────────────────────────────────

def invoke_supervisor(
    message: str,
    session_id: str
):

    if not SUPERVISOR_ID:

        print(
            "\n[ERROR] SUPERVISOR_AGENT_ID "
            "not set in .env"
        )

        sys.exit(1)

    bedrock = boto3.client(
        "bedrock-agent-runtime",
        region_name=REGION
    )

    print("\n" + "=" * 70)

    print(
        "SIGMA INTELLIGENCE PLATFORM — "
        "SUPERVISOR AGENT"
    )

    print("=" * 70)

    print(f"Agent     : {SUPERVISOR_ID}")

    print(f"Session   : {session_id}")

    print(
        f"Triggered : "
        f"{datetime.now().strftime('%H:%M:%S')}"
    )

    print("=" * 70)

    print(f"\nINPUT:\n{message}\n")

    print("-" * 70)

    start = time.time()

    # ── Langfuse Trace ─────────────────────────────────────

    lf_trace = (

        _lf.trace(

            name="sigma-supervisor",

            session_id=session_id,

            input={
                "message": message
            },

            tags=[
                "bedrock-agent",
                "azure-platform",
                "sigma-platform",
            ],

        )

        if _lf else None
    )

    try:

        response = bedrock.invoke_agent(

            agentId=SUPERVISOR_ID,

            agentAliasId=SUPERVISOR_ALIAS,

            sessionId=session_id,

            inputText=message,
        )

        # ── Stream Agent Reasoning ─────────────────────────

        for event in response["completion"]:

            # Agent reasoning text
            if "chunk" in event:

                text = (
                    event["chunk"]["bytes"]
                    .decode("utf-8")
                )

                print(
                    text,
                    end="",
                    flush=True
                )

            # Trace / orchestration events
            elif "trace" in event:

                trace = (
                    event["trace"]
                    .get("trace", {})
                )

                orch = trace.get(
                    "orchestrationTrace",
                    {}
                )

                # ── Supervisor reasoning ───────────────

                if "rationale" in orch:

                    rat = orch["rationale"].get(
                        "text",
                        ""
                    )

                    if rat:

                        ts = datetime.now().strftime(
                            "%H:%M:%S"
                        )

                        print(
                            f"\n[{ts}] "
                            f"SUPERVISOR REASONING:\n"
                            f"{rat[:180]}...\n"
                        )

                # ── Tool invocation ────────────────────

                inv = orch.get(
                    "invocationInput",
                    {}
                )

                if "actionGroupInvocationInput" in inv:

                    ag = inv[
                        "actionGroupInvocationInput"
                    ]

                    fn = ag.get(
                        "function",
                        "?"
                    )

                    ts = datetime.now().strftime(
                        "%H:%M:%S"
                    )

                    print(
                        f"[{ts}] TOOL CALLED: {fn}"
                    )

                    if lf_trace:

                        lf_trace.event(

                            name="tool-called",

                            input={
                                "tool": fn,
                                "timestamp": ts,
                            }
                        )

                # ── Tool output ────────────────────────

                obs = orch.get(
                    "observation",
                    {}
                )

                if "actionGroupInvocationOutput" in obs:

                    out = obs[
                        "actionGroupInvocationOutput"
                    ].get(
                        "text",
                        ""
                    )

                    if out:

                        ts = datetime.now().strftime(
                            "%H:%M:%S"
                        )

                        try:

                            parsed = json.loads(out)

                            for key in [

                                "status",

                                "root_cause_hypothesis",

                                "gmv_gap_inr",

                                "rows_loaded",

                                "alert_name",
                            ]:

                                if key in parsed:

                                    print(
                                        f"[{ts}] RESULT:\n"
                                        f"{key} = {parsed[key]}"
                                    )

                                    break

                        except Exception:

                            print(
                                f"[{ts}] RESULT:\n"
                                f"{out[:150]}"
                            )

                # ── Sub-agent delegation ───────────────

                if "agentCollaboratorInvocationInput" in inv:

                    collab = inv[
                        "agentCollaboratorInvocationInput"
                    ]

                    ts = datetime.now().strftime(
                        "%H:%M:%S"
                    )

                    agent_name = collab.get(
                        "agentCollaboratorName",
                        "?"
                    )

                    agent_input = collab.get(
                        "input",
                        {}
                    ).get(
                        "text",
                        ""
                    )

                    print(
                        f"\n[{ts}] "
                        f"DELEGATING TO: {agent_name}\n"
                        f"Reason: {agent_input[:120]}\n"
                    )

                    if lf_trace:

                        lf_trace.event(

                            name="agent-delegated",

                            input={
                                "agent": agent_name,
                                "message": agent_input[:200],
                                "timestamp": ts,
                            }
                        )

    except Exception as e:

        print(
            f"\n[ERROR] Agent invocation failed:\n{e}"
        )

        print("\nChecks:\n")

        print(
            "1. SUPERVISOR_AGENT_ID "
            "is correct"
        )

        print(
            "2. Bedrock Agent "
            "is in PREPARED state"
        )

        sys.exit(1)

    elapsed = round(
        time.time() - start,
        1
    )

    # ── Finalise Langfuse ─────────────────────────────────

    if lf_trace:

        lf_trace.update(

            output={
                "duration_seconds": elapsed,
                "status": "complete",
            }
        )

        _lf.flush()

    print("\n" + "=" * 70)

    print(
        f"AGENT COMPLETE | Duration: {elapsed}s"
    )

    print("=" * 70)

    print(
        "\nIncident reports generated successfully."
    )

    if _lf and lf_trace:

        print(
            f"\nLangfuse trace:\n"
            f"https://cloud.langfuse.com/trace/{lf_trace.id}"
        )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():

    parser = argparse.ArgumentParser(

        description=(
            "Sigma Intelligence Platform "
            "Pipeline Trigger"
        )
    )

    parser.add_argument(

        "--message",

        default=INCIDENT_MESSAGE
    )

    parser.add_argument(

        "--mode",

        choices=[
            "incident",
            "clean"
        ],

        default="incident"
    )

    parser.add_argument(

        "--health-check",

        action="store_true"
    )

    args = parser.parse_args()

    # ── Health Check ────────────────────────────────────

    if args.health_check:

        health_check()

        return

    # ── Select Mode ─────────────────────────────────────

    if args.mode == "clean":

        msg = CLEAN_MESSAGE

    elif args.message != INCIDENT_MESSAGE:

        msg = args.message

    else:

        msg = INCIDENT_MESSAGE

    session_id = (

        f"sigma-"
        f"{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )

    invoke_supervisor(
        msg,
        session_id
    )


if __name__ == "__main__":

    main()

