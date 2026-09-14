"""Central configuration loaded from environment variables / .env for AgentHR."""
from __future__ import annotations

import os
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Settings:
    """Runtime settings for AgentHR. Values come from the environment (see .env.example)."""

    def __init__(self) -> None:
        # --- AWS / Bedrock Settings ---
        self.aws_region: str = os.getenv("AWS_REGION", "us-east-1")
        # Primary default Amazon Bedrock model: Amazon Nova Pro (supports reasoning, tool use, multimodality)
        self.bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0")
        self.llm_backend: str = os.getenv("LLM_BACKEND", "bedrock").lower()

        # --- Data Store Settings ---
        # memory -> in-process store (offline demo / smoke test); dynamodb -> AWS DynamoDB
        self.store_backend: str = os.getenv("STORE_BACKEND", "memory").lower()
        self.dynamodb_table_prefix: str = os.getenv("DYNAMODB_TABLE_PREFIX", "agenthr_")
        self.dynamodb_endpoint_url: str = os.getenv("DYNAMODB_ENDPOINT_URL", "")

        # --- Application Server ---
        self.app_host: str = os.getenv("APP_HOST", "0.0.0.0")
        self.app_port: int = int(os.getenv("APP_PORT", "8080"))

        # --- Authentication ---
        self.admin_email: str = os.getenv("ADMIN_EMAIL", "hr@agenthr.ai")
        self.admin_password: str = os.getenv("ADMIN_PASSWORD", "admin123")
        self.secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")

        # --- Agent Operation ---
        # 1 -> full autonomous pipeline via Strands Agents SDK; 0 -> deterministic executor
        self.agent_autonomous: bool = os.getenv("AGENT_AUTONOMOUS", "1") == "1"
        # 1 -> Human-In-The-Loop approval gate active before outward actions; 0 -> bypass
        self.enable_approval_gate: bool = os.getenv("ENABLE_APPROVAL_GATE", "1") == "1"

    @property
    def is_mock_llm(self) -> bool:
        return self.llm_backend == "mock"

    @property
    def is_memory_store(self) -> bool:
        return self.store_backend == "memory"

    @property
    def is_dynamodb_store(self) -> bool:
        return self.store_backend == "dynamodb"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
