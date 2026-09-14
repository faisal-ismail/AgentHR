"""FastAPI application entry point for AgentHR & Bedrock AgentCore Runtime."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    class FastAPI:  # type: ignore
        def __init__(self, *args, **kwargs) -> None: pass
        def add_middleware(self, *args, **kwargs) -> None: pass
        def include_router(self, *args, **kwargs) -> None: pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f

    class CORSMiddleware:  # type: ignore
        pass

from app.api.routes import router
from app.services.event_service import seed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agenthr")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        seed()
        logger.info("AgentHR seeded (admin user + demo job).")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Seeding skipped: %s", exc)
    yield


app = FastAPI(
    title="AgentHR",
    description="Autonomous Recruiting Coordinator Agent with Supervised Human Checkpoints (Strands + Amazon Bedrock).",
    version="1.0.0",
    lifespan=lifespan,
)

# Streamlit frontend and API can be accessed from different origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {
        "name": "AgentHR",
        "tagline": "Autonomous recruiting coordinator with supervised approval checkpoints.",
        "framework": "Strands Agents SDK",
        "model": "Amazon Nova Pro (Amazon Bedrock)",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    from app.config import settings

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=False)
