#!/bin/sh
# AgentHR — single-container launcher (FastAPI + Streamlit).
# Compatible with AWS App Runner, ECS, and Bedrock AgentCore.
set -e

# --- Backend (FastAPI) — internal only, on :8080 --------------------------
# The Streamlit server makes requests to it server-side, so it never needs to
# be reachable from outside the container.
uvicorn app.main:app --host 0.0.0.0 --port 8080 &
API_PID=$!

echo "Waiting for the API on :8080 ..."
until python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health', timeout=1)" >/dev/null 2>&1; do
  if ! kill -0 $API_PID >/dev/null 2>&1; then
    echo "ERROR: FastAPI process died during startup."
    exit 1
  fi
  sleep 1
done
echo "API is up."

# --- Frontend (Streamlit) — public, on $PORT --------------------------
export BACKEND_URL="http://localhost:8080"
# Run on $PORT — Elastic Beanstalk AL2023 routes to 8000 by default
exec streamlit run frontend/streamlit_app.py \
  --server.headless=true \
  --server.address=0.0.0.0 \
  --server.port="${PORT:-8000}" \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false \
  --server.fileWatcherType=none
