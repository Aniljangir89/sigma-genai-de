FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dashboard files
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./

# Streamlit config — disable telemetry, set theme
RUN mkdir -p /app/.streamlit
COPY .streamlit/ /app/.streamlit/ 2>/dev/null || true

# Expose Streamlit port (NOTE: App Runner uses 8501 — set port in App Runner config)
EXPOSE 8501

# AWS credentials + Azure connection string come from App Runner env vars at runtime
# DO NOT hardcode credentials in this image

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
  "--server.port=8501", \
  "--server.address=0.0.0.0", \
  "--server.headless=true", \
  "--browser.gatherUsageStats=false"]
