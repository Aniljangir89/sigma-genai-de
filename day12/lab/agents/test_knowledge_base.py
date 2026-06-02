
"""
Test Bedrock Knowledge Base retrieval.
Run this twice — before and after the incident — to see RAG in action.

First run:
    knowledge base may be empty or contain only seeded documents.

Second run:
    today's incident report is indexed and retrieved.

This demonstrates:
    AI operational memory + historical incident retrieval.
"""

import argparse
import boto3
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

KB_ID = os.getenv("KNOWLEDGE_BASE_ID", "")

if not KB_ID:

    print(
        "Set KNOWLEDGE_BASE_ID in .env"
    )

    sys.exit(1)


parser = argparse.ArgumentParser()

parser.add_argument(

    "--query",

    default=(
        "Azure Function deployment caused "
        "Snowflake schema mismatch"
    )
)

args = parser.parse_args()


# ── Bedrock Knowledge Base Client ───────────────────────────────────────────

bedrock_kb = boto3.client(

    "bedrock-agent-runtime",

    region_name=REGION
)


print(
    "\nBEDROCK KNOWLEDGE BASE RETRIEVAL TEST"
)

print("=" * 60)

print(
    f"Knowledge Base ID : {KB_ID}"
)

print(
    f"Query             : {args.query}"
)

print("=" * 60)


try:

    resp = bedrock_kb.retrieve(

        knowledgeBaseId=KB_ID,

        retrievalQuery={
            "text":
                args.query
        },

        retrievalConfiguration={

            "vectorSearchConfiguration": {

                "numberOfResults":
                    3
            }
        },
    )

    results = resp.get(
        "retrievalResults",
        []
    )

    if not results:

        print(
            "\nNo results found.\n"
        )

        print(
            "First run:\n"
            "  Knowledge base contains only "
            "seeded documents.\n"
        )

        print(
            "Run the Supervisor Agent first.\n"
        )

        print(
            "Second run:\n"
            "  today's incident report "
            "will be retrieved here.\n"
        )

    else:

        print(
            f"\nFound {len(results)} result(s):\n"
        )

        for i, result in enumerate(results, 1):

            content = result.get(
                "content",
                {}
            ).get(
                "text",
                ""
            )

            location = result.get(
                "location",
                {}
            ).get(
                "s3Location",
                {}
            ).get(
                "uri",
                "?"
            )

            score = result.get(
                "score",
                0
            )

            print(
                f"[{i}] Score: {score:.3f}"
            )

            print(
                f"    Source: {location}"
            )

            print(
                f"    Content: "
                f"{content[:200]}..."
            )

            print()

    print("=" * 60)

    print("\nWhat this demonstrates:\n")

    print(
        "Run 1 (before incident):\n"
        "  generic documents only\n"
    )

    print(
        "Run 2 (after incident):\n"
        "  incident report indexed and retrieved\n"
    )

    print(
        "The Forensics Agent sees this context\n"
        "before calling Azure Monitor.\n"
    )

    print(
        "The agent already understands\n"
        "historical failure patterns.\n"
    )

    print(
        "Investigation becomes faster,\n"
        "more accurate,\n"
        "and historically informed.\n"
    )

except Exception as e:

    print(f"\n[ERROR] {e}")

    print("\nChecks:\n")

    print(
        "1. KNOWLEDGE_BASE_ID "
        "in .env is correct"
    )

    print(
        "2. Knowledge base is ACTIVE "
        "in Bedrock console"
    )

    print(
        "3. IAM role includes "
        "bedrock:Retrieve permission"
    )

