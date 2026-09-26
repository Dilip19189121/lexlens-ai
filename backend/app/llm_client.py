"""
llm_client.py — LLM provider layer with multi-key rotation and fallback.

Call chain (in order):
    Groq key #1 -> Groq key #2 -> ... -> Groq key #N (each with a per-key
    model fallback) -> Gemini (free-tier fallback) -> None (raise)

A provider call is abandoned and the next key/provider is tried when:
  - the response is HTTP 429 (rate limit) or 401/403 (invalid key), or
  - the request times out / the provider is unreachable (5xx, network).

All calls go through plain `httpx` (no vendor SDKs) to keep the dependency
footprint small and the two request shapes easy to audit.
"""

import time
from typing import List, Optional

import httpx

from . import config

# Exception type both for network failures and for deliberate "try the next
# provider" signals inside the rotation loop.
class ProviderError(Exception):
    """A provider call failed in a way that justifies trying the next one."""


def _is_retryable_status(status: int) -> bool:
    """Classify an HTTP status as 'move to the next provider' (True) or not.

    429 → rate limited (the core case this module exists for).
    401/403 → key invalid/exhausted — no point retrying the same key.
    5xx → provider-side trouble, next key may be healthier.
    400/413/422 → our request is malformed; rotating keys won't help, but we
    still raise so the caller surfaces a clean error.
    """
    return status in (429, 401, 403) or status >= 500


def _groq_chat(messages: List[dict], api_key: str, model: str) -> str:
    """Call Groq's OpenAI-compatible chat completions endpoint with one key.

    Returns the assistant's message text. Raises ProviderError with the HTTP
    status embedded if the call fails for a retryable reason.
    """
    try:
        response = httpx.post(
            config.GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.1,  # low → deterministic, schema-compliant JSON
                "max_tokens": 4096,
            },
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise ProviderError(f"groq network error: {exc}") from exc

    if response.status_code != 200:
        raise ProviderError(f"groq HTTP {response.status_code}: {response.text[:200]}")
    return response.json()["choices"][0]["message"]["content"]


def _gemini_chat(system_prompt: str, user_prompt: str, api_key: str) -> str:
    """Call Google's Gemini generateContent endpoint (free-tier fallback).

    Gemini uses `systemInstruction` for the system prompt and
    `responseMimeType: application/json` to bias output toward valid JSON.
    Returns the first candidate's text. Raises ProviderError on retryable
    failures, mirroring _groq_chat.
    """
    url = config.GEMINI_API_URL_TMPL.format(model=config.GEMINI_MODEL)
    try:
        response = httpx.post(
            url,
            headers={"x-goog-api-key": api_key},
            json={
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.1,
                    "maxOutputTokens": 8192,
                },
            },
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise ProviderError(f"gemini network error: {exc}") from exc

    if response.status_code != 200:
        raise ProviderError(f"gemini HTTP {response.status_code}: {response.text[:200]}")
    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise ProviderError(f"gemini unexpected response shape: {response.text[:200]}") from exc


def _mock_chat(user_prompt: str) -> str:
    """Return canned findings so the pipeline can be demoed with no API keys.

    Enabled via LLM_MOCK_MODE=true; echoes the JSON schema the real providers
    are prompted to produce, using clearly fake clause text.
    """
    import json

    return json.dumps(
        [
            {
                "clause_name": "Termination Notice",
                "risk_level": "HIGH",
                "quote": "Client may terminate this Agreement at any time, "
                "for any reason, with zero (0) days written notice and without "
                "payment of any outstanding fees.",
                "plain_summary": "The client can end the contract instantly "
                "without warning and without paying what they already owe you.",
                "action_step": "Negotiate a minimum 14-day written notice "
                "period and payment of all work completed to date.",
            },
            {
                "clause_name": "Liability Cap",
                "risk_level": "MEDIUM",
                "quote": "In no event shall the total liability of either party "
                "exceed the fees paid under this Agreement in the preceding "
                "three (3) months.",
                "plain_summary": "If something goes badly wrong, any payout is "
                "capped at just three months of fees.",
                "action_step": "Request a liability floor equal to at least "
                "twelve months of fees, with carve-outs for IP infringement.",
            },
        ]
    )


def call_llm(system_prompt: str, user_prompt: str) -> tuple:
    """Run the full rotation chain until one call succeeds.

    Args:
        system_prompt: instructions enforcing the strict JSON schema.
        user_prompt: the contract text chunk to analyze.

    Returns:
        (text, provider_label) — raw model text and which provider/key
        produced it, e.g. 'groq:key#1' or 'gemini'. Used for /health-style
        debugging and surfaced to the client in AnalyzeResponse.

    Raises:
        ProviderError: if every configured provider/key was exhausted.
        RuntimeError: if no providers are configured at all.
    """
    # Mock mode short-circuits the chain entirely — zero-cost demo path.
    if config.LLM_MOCK_MODE:
        return _mock_chat(user_prompt), "mock"

    # Build the ordered attempt list.
    attempts = []
    # Pass 1: every Groq key on the primary model. A 429 on one key moves
    # straight to the next key — the multi-account fallback this module exists
    # for. No time is wasted re-trying the same rate-limited key.
    for i, key in enumerate(config.GROQ_API_KEYS, start=1):
        attempts.append(
            (f"groq:key#{i}", lambda k=key: _groq_chat(
                _build_messages(system_prompt, user_prompt), k, config.GROQ_MODEL
            ))
        )
    # Pass 2: every Groq key again on the smaller fallback model. Groq rate
    # limits are per-model, so this often still has headroom after pass 1 is
    # exhausted — but it only runs once all keys have had their chance.
    for i, key in enumerate(config.GROQ_API_KEYS, start=1):
        attempts.append(
            (f"groq:key#{i}({config.GROQ_MODEL_FALLBACK})", lambda k=key: _groq_chat(
                _build_messages(system_prompt, user_prompt), k, config.GROQ_MODEL_FALLBACK
            ))
        )
    # Last resort: Gemini free tier (separate quota from Groq entirely).
    if config.GEMINI_API_KEY:
        attempts.append(
            ("gemini", lambda: _gemini_chat(system_prompt, user_prompt, config.GEMINI_API_KEY))
        )

    if not attempts:
        raise RuntimeError(
            "No LLM providers configured. Set GROQ_API_KEY_1 / GEMINI_API_KEY "
            "in backend/.env, or set LLM_MOCK_MODE=true."
        )

    last_error: Optional[Exception] = None
    for label, attempt in attempts:
        for retry in range(config.MAX_RETRIES_PER_PROVIDER):
            try:
                return attempt(), label
            except ProviderError as exc:
                last_error = exc
                # Brief backoff before using another retry on the SAME key —
                # mostly helps transient 429 bursts and 5xx blips.
                time.sleep(config.RETRY_BACKOFF_SECONDS * (retry + 1))

    raise ProviderError(f"All providers exhausted. Last error: {last_error}")


def _build_messages(system_prompt: str, user_prompt: str) -> List[dict]:
    """Shape the Groq (OpenAI-style) messages list from system+user prompts."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
