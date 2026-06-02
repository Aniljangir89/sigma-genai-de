import os
import json
import boto3
import phoenix as px
from openinference.instrumentation.bedrock import BedrockInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# ── 1. LAUNCH PHOENIX LOCAL COLLECTOR ──
print("Launching local Phoenix tracing server...")
session = px.launch_app(port=6006)

# ── 2. INITIALIZE OPENTELEMETRY TRACING ──
# Setup OpenTelemetry provider to export spans to our local Phoenix endpoint
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter("http://localhost:6006/v1/traces")))
trace.set_tracer_provider(provider)

# ── 3. AUTOMATICALLY INSTRUMENT BEDROCK CALLS ──
# This hook intercepts boto3 bedrock calls automatically under the hood
BedrockInstrumentor().instrument()

# ── 4. RUN LLM INFERENCE (Your Bedrock Application) ──
def run_support_agent():
    print("\nRunning support agent inquiry...")
    
    # Try to use actual Bedrock, but fall back to mock if credentials unavailable
    try:
        bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
        
        # Target AWS Bedrock Nova model
        model_id = "amazon.nova-lite-v1:0"
        
        # Nova model uses Messages API format
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": "I was charged $50.00 twice for order #1048. I want a refund."
                        }
                    ]
                }
            ],
            "inferenceConfig": {
                "temperature": 0.5,
                "maxTokens": 500
            }
        }
        
        response = bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps(body)
        )
        
        response_body = json.loads(response.get("body").read().decode("utf-8"))
        output_text = response_body.get("output", {}).get("message", {}).get("content", [{}])[0].get("text", "No response text")
        print(f"\nResponse from LLM:\n{output_text}")
        
    except Exception as e:
        print(f"\n⚠️  Bedrock call failed (likely missing AWS credentials): {e}")
        print("Using mock response for demonstration...")
        # Simulate a response for demonstration purposes
        print("\nResponse from LLM (mock):\nI understand your frustration. I've located your account and can see the duplicate charge of $50.00 on order #1048. I'm immediately processing a refund to your original payment method. The refund should appear within 3-5 business days. Is there anything else I can help you with?")

if __name__ == "__main__":
    # Run the LLM call which will trigger OTel tracing
    run_support_agent()
    
    print("\nKeep this script running so the Phoenix server stays active!")
    print("Press Ctrl+C to exit when you are done.")
    
    # Keep the server alive so you can inspect the dashboard
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down tracing server.")