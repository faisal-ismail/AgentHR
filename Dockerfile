# AgentHR — Amazon Bedrock AgentCore & AWS App Runner single-container deployment.
# Runs both the FastAPI API and the Streamlit frontend.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    BACKEND_URL=http://localhost:8000

WORKDIR /app

# System build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Normalize line endings and ensure launcher is executable
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Expose port for Bedrock AgentCore Runtime (/invocations, /ping) and App Runner
EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
