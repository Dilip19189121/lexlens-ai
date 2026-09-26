# LexLens AI — Backend

FastAPI service that accepts a contract PDF, extracts its text, and returns
structured risk findings per clause:

```json
{
  "clause_name": "Termination Notice",
  "risk_level": "HIGH",
  "quote": "Client may terminate with 0 days notice without compensation.",
  "plain_summary": "They can cancel on you instantly without paying you anything extra.",
  "action_step": "Request a minimum 14-day written notice requirement."
}
```

## Run locally

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# .venv/bin/python -m pip install -r requirements.txt     # macOS/Linux

cp .env.example .env        # then paste your real keys into .env
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs

> No keys yet? Set `LLM_MOCK_MODE=true` in `.env` to run the whole pipeline
> with canned findings — handy for frontend development.

## Environment variables

Copy `.env.example` to `.env` (git-ignored) and fill in:

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, ... | yes | Groq keys, rotated in order |
| `GEMINI_API_KEY` | yes | Gemini free-tier fallback |
| `GROQ_MODEL` / `GROQ_MODEL_FALLBACK` | no | Groq model IDs (defaults: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`) |
| `GEMINI_MODEL` | no | Gemini model ID (default: `gemini-2.5-flash`) |
| `LLM_MOCK_MODE` | no | `true` = canned responses, no API calls |

## API

### `GET /health`
Returns status and which providers are configured, e.g.
`{"status": "ok", "providers": "groq x2 -> gemini"}`.

### `POST /analyze`
`multipart/form-data` with a `file` field containing a PDF.

- `200` → `{filename, total_pages, findings: [...], provider_used}`
  (findings sorted HIGH → MEDIUM → LOW → SAFE)
- `400` → bad upload (empty, not a PDF, > 10 MB, unreadable, no text layer)
- `502` → all AI providers failed (rate limits or outage)

## Architecture

```
app/
├── config.py      env loading, key discovery, tunables
├── schemas.py     Pydantic models — the clause JSON contract
├── extractor.py   pdfplumber text extraction + upload validation
├── llm_client.py  provider calls, key rotation, retry/backoff, mock mode
├── analyzer.py    system prompt, chunking, JSON salvage/parsing
├── routes.py      POST /analyze handler
└── main.py        FastAPI app setup, CORS, /health
```

**Fallback chain** (per LLM call, on 429 / 401 / 403 / 5xx / timeout):

```
Groq key #1 → Groq key #2 → ... (primary model)
→ Groq key #1 → Groq key #2 → ... (fallback model)
→ Gemini (free tier)
```

Keys are tried in order before any model switch, so a rate-limited key never
wastes retries. Two short backoff attempts happen per key for transient 5xx.

**Phase 2 note:** the local pattern matcher (CUAD/UnfairToS keywords) will
slot in front of the LLM call in `analyzer.analyze_contract_text`, so known
clauses return instantly with zero API cost.

## Tests

```bash
backend/.venv/Scripts/python scripts/smoke_test.py
```

Runs 15 offline checks: full `/analyze` pipeline on a generated sample PDF,
upload validation errors, and the key-rotation chain with monkeypatched HTTP.
