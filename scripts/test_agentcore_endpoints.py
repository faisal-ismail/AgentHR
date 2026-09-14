"""Test suite for Amazon Bedrock AgentCore Runtime endpoints.

Verifies:
  - GET /ping returns 200 OK and Healthy status
  - POST /invocations responds to AgentCore Runtime requests
  - GET /api/health returns AgentHR status
"""
from __future__ import annotations

import os
import sys

os.environ["STORE_BACKEND"] = "memory"
os.environ["LLM_BACKEND"] = "mock"
os.environ["AGENT_AUTONOMOUS"] = "0"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    HAS_TESTCLIENT = True
except ImportError:
    HAS_TESTCLIENT = False


def test_agentcore_ping():
    print("Testing GET /ping (AgentCore Liveness Health Check)...")
    if HAS_TESTCLIENT:
        resp = client.get("/ping")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
    else:
        from app.api.routes import agentcore_ping
        data = agentcore_ping()

    assert data.get("status") == "Healthy", f"Expected Healthy, got {data}"
    print("  ✓ GET /ping passed!")


def test_agentcore_invocations():
    print("Testing POST /invocations (AgentCore Invocation Endpoint)...")
    payload = {"prompt": "Ping check"}
    if HAS_TESTCLIENT:
        resp = client.post("/invocations", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
    else:
        from app.api.routes import agentcore_invocations
        data = agentcore_invocations(payload)

    assert data.get("statusCode") == 200
    assert "AgentHR" in data.get("response", "")
    print("  ✓ POST /invocations passed!")


def test_agent_health():
    print("Testing GET /api/health...")
    if HAS_TESTCLIENT:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
    else:
        from app.api.routes import health
        data = health()

    assert data.get("status") == "ok"
    assert "Strands" in data.get("agent", "")
    print("  ✓ GET /api/health passed!")


if __name__ == "__main__":
    test_agentcore_ping()
    test_agentcore_invocations()
    test_agent_health()
    print("\nALL AGENTCORE ENDPOINT TESTS PASSED!")

