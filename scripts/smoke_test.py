"""
smoke_test.py — End-to-end Phase 1 verification without real API keys.

What it covers:
  1. Sample PDF generation (if missing).
  2. Full POST /analyze pipeline via FastAPI's TestClient in LLM_MOCK_MODE:
     upload validation -> pdfplumber extraction -> chunking -> mock LLM ->
     strict JSON parse -> schema validation -> sorted findings.
  3. The key-rotation chain: Groq 429s must fall through to Gemini (both
     HTTP layers monkeypatched, no network calls).

Usage (from repo root):
    backend/.venv/Scripts/python scripts/smoke_test.py
"""

import json
import os
import sys
from pathlib import Path

# Mock mode must be set before the backend config module is imported.
os.environ["LLM_MOCK_MODE"] = "true"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
# LLM_MOCK_MODE=true is set via the environment (top of file) BEFORE any app
# import, so the endpoint test below runs fully offline.

SAMPLE_PDF = REPO_ROOT / "backend" / "samples" / "sample_contract.pdf"

failures = []


def check(name: str, condition: bool, extra: str = "") -> None:
    """Record and print one pass/fail assertion."""
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {extra}" if extra else ""))
    if not condition:
        failures.append(name)


def test_analyze_endpoint(client: TestClient) -> None:
    """Upload the sample PDF and verify the full response contract."""
    print("\n1. POST /analyze with sample_contract.pdf (mock mode)")
    with SAMPLE_PDF.open("rb") as fh:
        response = client.post(
            "/analyze",
            files={"file": ("sample_contract.pdf", fh, "application/pdf")},
        )
    check("HTTP 200", response.status_code == 200, f"got {response.status_code}: {response.text[:300]}")
    body = response.json()

    check("filename echoed", body.get("filename") == "sample_contract.pdf")
    check("page count parsed", body.get("total_pages") == 1, f"got {body.get('total_pages')}")
    check("mock provider reported", body.get("provider_used") == "mock", f"got {body.get('provider_used')}")

    findings = body.get("findings", [])
    check("findings returned", len(findings) >= 1, f"got {len(findings)}")

    # PRD schema: exactly these five keys per finding.
    expected_keys = {"clause_name", "risk_level", "quote", "plain_summary", "action_step"}
    all_keys_ok = all(set(f.keys()) == expected_keys for f in findings)
    check("every finding matches PRD schema", all_keys_ok)

    # Sorting: worst risks first (HIGH -> MEDIUM -> LOW -> SAFE).
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "SAFE": 3}
    levels = [f["risk_level"] for f in findings]
    check("findings sorted HIGH->SAFE", levels == sorted(levels, key=lambda l: order.get(l, 4)), str(levels))


def test_validation_errors(client: TestClient) -> None:
    """Non-PDF and empty uploads must fail with clean 400s."""
    print("\n2. Upload validation")
    response = client.post("/analyze", files={"file": ("notes.txt", b"hello", "text/plain")})
    check("non-PDF rejected with 400", response.status_code == 400, f"got {response.status_code}")
    response = client.post("/analyze", files={"file": ("empty.pdf", b"", "application/pdf")})
    check("empty file rejected with 400", response.status_code == 400, f"got {response.status_code}")


def test_key_rotation() -> None:
    """Groq 429 must fall through the chain; Gemini succeeding ends it."""
    print("\n3. Key rotation (monkeypatched, no network)")
    from app import config, llm_client

    calls = []

    def fake_groq(messages, api_key, model):
        calls.append(f"groq:{api_key[-4:]}:{model}")
        raise llm_client.ProviderError("groq HTTP 429: rate limit")

    def fake_gemini(system_prompt, user_prompt, api_key):
        calls.append(f"gemini:{api_key[-4:]}")
        return json.dumps(
            [{"clause_name": "X", "risk_level": "HIGH", "quote": "q",
              "plain_summary": "s", "action_step": "a"}]
        )

    real_groq, real_gemini = llm_client._groq_chat, llm_client._gemini_chat
    llm_client._groq_chat = fake_groq
    llm_client._gemini_chat = fake_gemini
    # Two fake Groq keys + one fake Gemini key, no sleeps during the test.
    real_cfg = (
        llm_client.config.GROQ_API_KEYS,
        llm_client.config.GEMINI_API_KEY,
        llm_client.config.MAX_RETRIES_PER_PROVIDER,
        llm_client.config.RETRY_BACKOFF_SECONDS,
    )
    llm_client.config.GROQ_API_KEYS = ["key-aaaa", "key-bbbb"]
    llm_client.config.GEMINI_API_KEY = "key-cccc"
    llm_client.config.MAX_RETRIES_PER_PROVIDER = 1
    llm_client.config.RETRY_BACKOFF_SECONDS = 0
    # Mock mode would short-circuit the provider chain entirely — turn it off
    # for this test only, then restore.
    original_mock = llm_client.config.LLM_MOCK_MODE
    llm_client.config.LLM_MOCK_MODE = False
    try:
        text, provider = llm_client.call_llm("system", "user")
    finally:
        llm_client._groq_chat, llm_client._gemini_chat = real_groq, real_gemini
        llm_client.config.LLM_MOCK_MODE = original_mock
        (
            llm_client.config.GROQ_API_KEYS,
            llm_client.config.GEMINI_API_KEY,
            llm_client.config.MAX_RETRIES_PER_PROVIDER,
            llm_client.config.RETRY_BACKOFF_SECONDS,
        ) = real_cfg

    check("groq key #1 tried first", calls[0].startswith("groq") and "aaaa" in calls[0], calls[0])
    check("groq key #2 tried second", "bbbb" in calls[1], calls[1])
    check("gemini used as last resort", calls[-1] == "gemini:cccc", calls[-1])
    check("result came from gemini", provider == "gemini", provider)
    check("response parsed to schema", json.loads(text)[0]["clause_name"] == "X")


def main() -> int:
    if not SAMPLE_PDF.exists():
        print("Generating sample PDF...")
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "make_sample_pdf", REPO_ROOT / "scripts" / "make_sample_pdf.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main()

    client = TestClient(app)
    test_analyze_endpoint(client)
    test_validation_errors(client)
    test_key_rotation()

    print(f"\n{'=' * 50}")
    if failures:
        print(f"SMOKE TEST FAILED — {len(failures)} check(s): {failures}")
        return 1
    print("ALL SMOKE TESTS PASSED [OK]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
