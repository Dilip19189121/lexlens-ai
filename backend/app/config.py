"""
config.py — Central configuration for the LexLens AI backend.

Loads environment variables from `backend/.env` (if present) and exposes them
as module-level constants. All API keys come from the environment — never
hard-code secrets here.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# `backend/` directory (this file lives in backend/app/).
BACKEND_DIR = Path(__file__).resolve().parent.parent

# Load backend/.env so `os.getenv` sees the keys during local development.
load_dotenv(BACKEND_DIR / ".env")


def _discover_groq_keys() -> list:
    """Collect all Groq API keys defined as GROQ_API_KEY_1, _2, _3, ... .

    Scans upward from index 1 and stops at the first missing index, so the
    rotation order matches the numbering in the .env file.
    """
    keys = []
    index = 1
    while True:
        value = os.getenv(f"GROQ_API_KEY_{index}", "").strip()
        if not value:
            break
        keys.append(value)
        index += 1
    return keys


# ── API keys ────────────────────────────────────────────────────────────────
GROQ_API_KEYS: list = _discover_groq_keys()
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

# ── Model IDs (all overridable via environment) ─────────────────────────────
# Groq: llama-3.x models became Enterprise-only in mid-2026, so the gpt-oss
# family is the free/cheap production choice. Try the big one first, then the
# smaller/faster one as a per-provider fallback.
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_MODEL_FALLBACK: str = os.getenv("GROQ_MODEL_FALLBACK", "openai/gpt-oss-20b")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ── Provider endpoints ──────────────────────────────────────────────────────
GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_API_URL_TMPL: str = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# ── Request / retry tuning ──────────────────────────────────────────────────
LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
MAX_RETRIES_PER_PROVIDER: int = int(os.getenv("MAX_RETRIES_PER_PROVIDER", "2"))
RETRY_BACKOFF_SECONDS: float = float(os.getenv("RETRY_BACKOFF_SECONDS", "1.5"))

# ── Upload / analysis limits ────────────────────────────────────────────────
MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024  # 10 MB PDF cap for the free tier
MAX_CHUNK_CHARS: int = 6000  # contract text chunk size sent per LLM call
CHUNK_OVERLAP_CHARS: int = 200  # overlap so clauses split across chunks survive

# ── Mock mode ───────────────────────────────────────────────────────────────
# When true, the LLM layer returns canned findings instead of calling APIs.
# Useful for demos, tests, and development without burning free-tier quota.
LLM_MOCK_MODE: bool = os.getenv("LLM_MOCK_MODE", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)


def provider_summary() -> str:
    """Human-readable summary of the configured provider chain (for /health)."""
    parts = [f"groq x{len(GROQ_API_KEYS)}"]
    if GEMINI_API_KEY:
        parts.append("gemini")
    if LLM_MOCK_MODE:
        parts.append("MOCK")
    return " -> ".join(parts) if parts else "none configured"
