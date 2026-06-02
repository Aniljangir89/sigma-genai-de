
import logging
import json
import os

from datetime import datetime

import azure.functions as func
from azure.storage.blob import BlobServiceClient


app = func.FunctionApp()


@app.event_hub_message_trigger(
    arg_name="event",
    event_hub_name="sigma-transactions",
    connection="EVENT_HUB_CONNECTION_STRING"
)

def eventhub_consumer(event: func.EventHubEvent):

    try:

        # ── Read Event ─────────────────────────────────────

        body = event.get_body().decode("utf-8")

        data = json.loads(body)

        logging.info(f"Received event: {data}")

        # ── Storage Connection ─────────────────────────────

        storage_connection_string = os.getenv(
            "AZURE_STORAGE_CONNECTION_STRING"
        )

        if not storage_connection_string:
            raise Exception(
                "AZURE_STORAGE_CONNECTION_STRING not found"
            )

        blob_service_client = (
            BlobServiceClient.from_connection_string(
                storage_connection_string
            )
        )

        # ── Blob Details ───────────────────────────────────

        timestamp = datetime.utcnow().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        transaction_id = data.get(
            "transaction_id",
            "unknown"
        )

        blob_name = (
            f"{timestamp}_{transaction_id}.json"
        )

        # ── Upload to Blob Storage ─────────────────────────

        blob_client = blob_service_client.get_blob_client(
            container="bronze",
            blob=blob_name
        )

        blob_client.upload_blob(
            json.dumps(data, indent=2),
            overwrite=True
        )

        logging.info(
            f"Uploaded to Blob Storage: {blob_name}"
        )

    except Exception as e:

        logging.error(
            f"ERROR processing event: {str(e)}"
        )
