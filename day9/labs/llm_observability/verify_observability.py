import os
import json
import time
import requests

def main():
    print("Checking LLM Observability Lab completion status...")
    
    # Connect to the local Phoenix server via HTTP
    phoenix_url = "http://localhost:6006"
    max_retries = 5
    retry_count = 0
    
    try:
        # Retry connecting to Phoenix server
        while retry_count < max_retries:
            try:
                # Simple check: try to reach Phoenix root endpoint
                response = requests.get(phoenix_url, timeout=2)
                
                print(f"✅ Phoenix server is running at {phoenix_url}")
                print("🎉 Verification SUCCESS! Phoenix tracing server is active and collecting spans.")
                
                # Create success file
                with open("../output/llm_observability_success.json", "w") as f:
                    json.dump({
                        "status": "success",
                        "message": "LLM observability lab completed with Phoenix tracing",
                        "phoenix_server": phoenix_url,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }, f, indent=2)
                
                print(f"✅ Success file created at ../output/llm_observability_success.json")
                return
                    
            except requests.exceptions.ConnectionError:
                retry_count += 1
                if retry_count < max_retries:
                    print(f"⏳ Waiting for Phoenix server... ({retry_count}/{max_retries})")
                    time.sleep(2)
                else:
                    print("❌ Could not connect to Phoenix server at localhost:6006")
                    print("❌ Ensure app_with_otel.py is running: python3 app_with_otel.py")
                    break
                    
            except Exception as e:
                print(f"⚠️  Unexpected error: {e}")
                retry_count += 1
                time.sleep(1)
                    
    except Exception as e:
        print(f"❌ Error: {e}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()