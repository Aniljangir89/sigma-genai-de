
"""
==============================================================================
TOOL: send_teams_alert.py
==============================================================================
Purpose:
    Sends incident alerts to Microsoft Teams webhook.

Features:
    - Severity-aware alerts
    - Agent notifications
    - Incident escalation
    - Human-in-the-loop visibility

Used by:
    * Supervisor Agent
    * Incident Report Agent
    * Recovery Agent

==============================================================================
"""

import json
import os
import requests

from datetime import datetime, timezone
from dotenv import load_dotenv


load_dotenv()


# ── Severity Labels ──────────────────────────────────────────────────────────

SEVERITY_LABELS = {

    "critical":
        "🚨 CRITICAL",

    "high":
        "⚠️ HIGH",

    "medium":
        "🟡 MEDIUM",

    "info":
        "ℹ️ INFO",
}


# ── Alert Logic ──────────────────────────────────────────────────────────────

def send_alert(
    message: str,
    severity: str = "high"
) -> dict:

    webhook_url = os.getenv(
        "TEAMS_WEBHOOK_URL"
    )

    if not webhook_url:

        return {
            "status":
                "SKIPPED",

            "reason":
                "TEAMS_WEBHOOK_URL not configured"
        }

    if not message:

        return {
            "status":
                "ERROR",

            "reason":
                "Empty message"
        }

    ts = datetime.now(
        timezone.utc
    ).isoformat()

    severity_text = SEVERITY_LABELS.get(
        severity.lower(),
        "⚠️ ALERT"
    )

    full_message = f"""
{severity_text} — Sigma Intelligence Platform

{message}

---
Severity  : {severity.upper()}
Timestamp : {ts}
Source    : Sigma Autonomous Recovery System
"""

    payload = {
        "text": full_message
    }

    try:

        response = requests.post(
            webhook_url,
            json=payload
        )

        if response.status_code in [200, 201]:

            return {

                "status":
                    "SENT",

                "severity":
                    severity,

                "sent_at":
                    ts,

                "channel":
                    "Microsoft Teams"
            }

        return {

            "status":
                "ERROR",

            "http_status":
                response.status_code,

            "response":
                response.text
        }

    except Exception as e:

        return {

            "status":
                "ERROR",

            "error":
                str(e)
        }


# ── Local Test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":

    test_message = (
        "TEST ALERT — Sigma Intelligence Platform "
        "notification pipeline validation."
    )

    result = send_alert(
        message=test_message,
        severity="info"
    )

    print(
        json.dumps(
            result,
            indent=2
        )
    )
