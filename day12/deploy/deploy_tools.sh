
#!/bin/bash

# =============================================================================
# SIGMA INTELLIGENCE PLATFORM — Deploy AI Tool Functions
# Azure + Bedrock Hybrid Architecture
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAB_DIR="$SCRIPT_DIR/../lab"
ENV_FILE="$LAB_DIR/.env"

# ── Load env vars safely ─────────────────────────────────────────────────────

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "[ERROR] $ENV_FILE not found."
    exit 1
fi

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ROLE="${LAMBDA_ROLE_ARN}"

if [ -z "$ROLE" ]; then
    echo "[ERROR] LAMBDA_ROLE_ARN not set in lab/.env"
    exit 1
fi

echo "========================================================"
echo "SIGMA INTELLIGENCE PLATFORM — TOOL DEPLOYMENT"
echo "========================================================"
echo "Region : $REGION"
echo "Role   : $ROLE"
echo "========================================================"

# ── Azure + Bedrock Tool Definitions ────────────────────────────────────────


TOOLS=(

    "sigma-tool-check-azure-monitor:tools/check_azure_monitor.py"

    "sigma-tool-get-eventhub-records:tools/get_eventhub_records.py"

    "sigma-tool-query-snowflake:tools/query_snowflake.py"

    "sigma-tool-rollback-function:tools/rollback_function_deployment.py"

    "sigma-tool-create-alert:tools/create_azure_alert.py"

    "sigma-tool-quarantine-rows:tools/quarantine_rows.py"

    "sigma-tool-load-snowflake:tools/load_to_snowflake.py"

    "sigma-tool-write-report:tools/write_incident_report.py"

    "sigma-tool-send-alert:tools/send_teams_alert.py"

    "sigma-mcp-server:mcp/sigma_mcp_server.py"
)


# ── Snowflake dependency tools ──────────────────────────────────────────────

SNOWFLAKE_TOOLS=(
    "sigma-tool-query-snowflake"
    "sigma-tool-load-snowflake"
)

needs_snowflake() {

    local name="$1"

    for t in "${SNOWFLAKE_TOOLS[@]}"; do

        [[ "$t" == "$name" ]] && return 0

    done

    return 1
}

TOTAL=${#TOOLS[@]}
COUNT=0

# ── Deploy Loop ─────────────────────────────────────────────────────────────

for ENTRY in "${TOOLS[@]}"; do

    FUNC_NAME="${ENTRY%%:*}"
    SOURCE_FILE="${ENTRY##*:}"
    FULL_PATH="$LAB_DIR/$SOURCE_FILE"

    COUNT=$((COUNT + 1))

    echo ""
    echo "[$COUNT/$TOTAL] Deploying $FUNC_NAME..."

    if [ ! -f "$FULL_PATH" ]; then

        echo "  [ERROR] Source not found: $FULL_PATH"
        exit 1

    fi

    ZIP_FILE="/tmp/${FUNC_NAME}.zip"
    HANDLER_NAME=$(basename "$SOURCE_FILE" .py)

    # ── Package dependencies ───────────────────────────────────────────────

    if needs_snowflake "$FUNC_NAME"; then

        echo "  Bundling snowflake-connector-python..."

        PKG_DIR="/tmp/pkg_${FUNC_NAME}"

        rm -rf "$PKG_DIR"
        mkdir -p "$PKG_DIR"

        pip install snowflake-connector-python \
            -t "$PKG_DIR/" \
            -q \
            --only-binary :all:

        cp "$FULL_PATH" "$PKG_DIR/${HANDLER_NAME}.py"

        rm -f "$ZIP_FILE"

        cd "$PKG_DIR"
        zip -qr "$ZIP_FILE" .
        cd - > /dev/null

        rm -rf "$PKG_DIR"

    else

        cp "$FULL_PATH" "/tmp/${HANDLER_NAME}.py"

        rm -f "$ZIP_FILE"

        cd /tmp
        zip -q "$ZIP_FILE" "${HANDLER_NAME}.py"
        cd - > /dev/null

        rm -f "/tmp/${HANDLER_NAME}.py"

    fi

    # ── Function exists? ───────────────────────────────────────────────────



if aws lambda get-function \
    --function-name "$FUNC_NAME" \
    --region "$REGION" > /dev/null 2>&1; then

    echo "  Updating existing function..."

    aws lambda update-function-code \
        --function-name "$FUNC_NAME" \
        --zip-file "fileb://$ZIP_FILE" \
        --region "$REGION" \
        > /dev/null

    # WAIT FOR CODE UPDATE
    aws lambda wait function-updated \
        --function-name "$FUNC_NAME" \
        --region "$REGION"

    aws lambda update-function-configuration \
        --function-name "$FUNC_NAME" \
        --timeout 120 \
        --memory-size 256 \
        --environment "Variables={

            AZURE_STORAGE_CONNECTION_STRING=${AZURE_STORAGE_CONNECTION_STRING:-},

            EVENT_HUB_CONNECTION_STRING=${EVENT_HUB_CONNECTION_STRING:-},

            EVENT_HUB_NAME=${EVENT_HUB_NAME:-},

            AZURE_FUNCTION_NAME=${AZURE_FUNCTION_NAME:-},

            SNOWFLAKE_ACCOUNT=${SNOWFLAKE_ACCOUNT:-},

            SNOWFLAKE_USER=${SNOWFLAKE_USER:-},

            SNOWFLAKE_PASSWORD=${SNOWFLAKE_PASSWORD:-},

            SNOWFLAKE_DATABASE=${SNOWFLAKE_DATABASE:-SIGMA},

            SNOWFLAKE_SCHEMA=${SNOWFLAKE_SCHEMA:-SILVER},

            SNOWFLAKE_WAREHOUSE=${SNOWFLAKE_WAREHOUSE:-SIGMA_WH},

            LAMBDA_ROLE_ARN=${LAMBDA_ROLE_ARN:-}
        }" \
        --region "$REGION" \
        > /dev/null

    # WAIT FOR CONFIG UPDATE
    aws lambda wait function-updated \
        --function-name "$FUNC_NAME" \
        --region "$REGION"

    echo "  Updated."

else

    echo "  Creating new function..."

    aws lambda create-function \
        --function-name "$FUNC_NAME" \
        --runtime python3.12 \
        --role "$ROLE" \
        --handler "${HANDLER_NAME}.lambda_handler" \
        --zip-file "fileb://$ZIP_FILE" \
        --timeout 120 \
        --memory-size 256 \
        --environment "Variables={

            AZURE_STORAGE_CONNECTION_STRING=${AZURE_STORAGE_CONNECTION_STRING:-},

            EVENT_HUB_CONNECTION_STRING=${EVENT_HUB_CONNECTION_STRING:-},

            EVENT_HUB_NAME=${EVENT_HUB_NAME:-},

            AZURE_FUNCTION_NAME=${AZURE_FUNCTION_NAME:-},

            SNOWFLAKE_ACCOUNT=${SNOWFLAKE_ACCOUNT:-},

            SNOWFLAKE_USER=${SNOWFLAKE_USER:-},

            SNOWFLAKE_PASSWORD=${SNOWFLAKE_PASSWORD:-},

            SNOWFLAKE_DATABASE=${SNOWFLAKE_DATABASE:-SIGMA},

            SNOWFLAKE_SCHEMA=${SNOWFLAKE_SCHEMA:-SILVER},

            SNOWFLAKE_WAREHOUSE=${SNOWFLAKE_WAREHOUSE:-SIGMA_WH},

            LAMBDA_ROLE_ARN=${LAMBDA_ROLE_ARN:-}
        }" \
        --region "$REGION" \
        > /dev/null

    aws lambda wait function-active \
        --function-name "$FUNC_NAME" \
        --region "$REGION"

    echo "  Created."

fi



    rm -f "$ZIP_FILE"

done

# ── Final Validation ────────────────────────────────────────────────────────

echo ""
echo "========================================================"
echo "ALL TOOLS DEPLOYED SUCCESSFULLY"
echo "========================================================"

echo ""
echo "Testing MCP discovery..."

cd "$LAB_DIR"

python mcp/test_mcp.py

echo ""
echo "Next:"
echo "  python trigger/pipeline_trigger.py --health-check"
echo "========================================================"

