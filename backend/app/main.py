"""
main.py — FastAPI application entry point for LexLens AI.

Run locally from the `backend/` directory with:
    uvicorn app.main:app --reload --port 8000

The API (POST /analyze, GET /health, /docs) and the frontend (frontend/
served at /) ship as ONE deployable service: opening http://localhost:8000/
serves the LexLens UI, which calls the API on the same origin.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, pattern_matcher
from .routes import router

# frontend/ lives one level above backend/app/ — this file is backend/app/main.py.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

if not FRONTEND_DIR.is_dir():
    raise RuntimeError(
        f"Frontend folder not found at {FRONTEND_DIR}. "
        "The frontend/ directory must sit next to backend/ in the repo root."
    )

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


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    """Serve the single-page frontend at the site root.

    no-store: the UI is one evolving HTML file whose inline JS calls the
    API — never let a browser or proxy pin a stale copy across deploys.
    """
    return FileResponse(FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-store"})


# Static assets (images, css, js) if the frontend grows beyond one file.
# Mounted last so /analyze, /health, /docs and / keep priority.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/health")
async def health() -> dict:
    """Liveness probe — also reports which LLM providers are configured."""
    return {
        "status": "ok",
        "app": "LexLens AI",
        "providers": config.provider_summary(),
        "pattern_rules": pattern_matcher.rules_count(),
    }
