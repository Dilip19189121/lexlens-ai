"""
main.py — FastAPI application entry point for LexLens AI.

Run locally from the `backend/` directory with:
    uvicorn app.main:app --reload --port 8000

Interactive docs are then at http://localhost:8000/docs
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routes import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lexlens")

app = FastAPI(
    title="LexLens AI",
    description="Scans legal contracts and flags risky clauses in plain language.",
    version="0.1.0",
)

# Permissive CORS for now: the React frontend will be served either from the
# same origin (static files) or a dev server (vite) on another port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# All API routes live in routes.py to keep this file focused on app setup.
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    """Liveness probe — also reports which LLM providers are configured."""
    return {
        "status": "ok",
        "app": "LexLens AI",
        "providers": config.provider_summary(),
    }
