"""
routes.py — API route handlers.

Currently just POST /analyze. The hybrid pattern-matching engine (Phase 2)
runs inside analyze_contract_text: known risky clauses are caught locally
with zero API cost; only unrecognized text reaches the LLM.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile

from . import extractor
from .analyzer import analyze_contract_text
from .llm_client import ProviderError
from .schemas import AnalyzeResponse

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_contract(file: UploadFile = File(...)) -> AnalyzeResponse:
    """Analyze an uploaded contract PDF and return structured risk findings.

    Pipeline: validate upload → extract text (pdfplumber) → local pattern
    matching (instant, no API) → LLM analysis of unmatched text with key
    rotation → strict JSON schema validation.

    Errors are returned as clean HTTP errors, never raw tracebacks:
      400 — bad file (empty, not a PDF, too large, unreadable, no text layer)
      502 — every LLM provider/key failed (rate limits, outages)
      500 — unexpected internal failure
    """
    filename = file.filename or "uploaded.pdf"

    # 1. Read the raw upload into memory (contracts are small; cap is 10 MB).
    data = await file.read()

    # 2. Validate + extract text.
    try:
        extractor.validate_pdf(data, filename)
        text, page_count = extractor.extract_text_from_pdf(data)
    except extractor.PdfExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 3. Run the hybrid risk-analysis pipeline: local pattern matching first
    #    (zero API cost), LLM (with key rotation) only for unrecognized text.
    try:
        findings, provider_used = analyze_contract_text(text)
    except ProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"All AI providers failed (rate limit or outage): {exc}",
        ) from exc
    except RuntimeError as exc:
        # No keys configured and mock mode off — a server setup problem.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AI returned unparseable output: {exc}",
        ) from exc

    # 4. Pydantic validates the exact schema before anything reaches the client.
    return AnalyzeResponse(
        filename=filename,
        total_pages=page_count,
        findings=findings,
        provider_used=provider_used,
    )
