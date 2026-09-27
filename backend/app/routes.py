"""
routes.py — API route handlers.

Currently just POST /analyze. The hybrid pattern-matching engine (Phase 2)
runs inside analyze_contract_text: known risky clauses are caught locally
with zero API cost; only unrecognized text reaches the LLM.

Multilingual: an optional `language` form field selects the output language
for plain_summary/action_step (default English). Non-English requests also
route the locally-matched findings through the LLM so the whole response is
in one language; quotes always stay verbatim from the source document.
"""

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from . import extractor
from .analyzer import analyze_contract_text
from .llm_client import ProviderError
from .schemas import AnalyzeResponse

router = APIRouter()

# Cap for pasted raw text — mirrors the frontend textarea's 40,000-char counter.
MAX_PASTE_CHARS = 40_000


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_contract(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    language: str = Form("English"),
) -> AnalyzeResponse:
    """Analyze a contract (PDF upload OR pasted text) → structured findings.

    Exactly one of `file` (a PDF upload) or `text` (pasted raw contract
    text) must be provided as multipart form fields. Pipeline: validate →
    extract text (pdfplumber for PDFs) → local pattern matching (instant,
    no API) → LLM analysis of unmatched text with key rotation → strict
    JSON schema validation.

    `language` (optional, default "English") selects the output language for
    plain_summary/action_step — e.g. "English", "Telugu", "Hindi". The
    response echoes it back so the frontend knows what was used; `quote` is
    always verbatim in the document's original language.

    Errors are returned as clean HTTP errors, never raw tracebacks:
      400 — no input, bad file (empty, not a PDF, too large, unreadable, no
            text layer), or pasted text over the size cap
      502 — every LLM provider/key failed (rate limits, outages)
      503 — no providers configured (server setup problem)
      500 — unexpected internal failure
    """
    pasted_text = (text or "").strip()
    has_file = file is not None and bool(file.filename)

    # 1. Get the raw document text from whichever input channel was used.
    if has_file:
        filename = file.filename or "uploaded.pdf"
        # Read the raw upload into memory (contracts are small; cap is 10 MB).
        data = await file.read()

        # Validate + extract text.
        try:
            extractor.validate_pdf(data, filename)
            doc_text, page_count = extractor.extract_text_from_pdf(data)
        except extractor.PdfExtractionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif pasted_text:
        if len(pasted_text) > MAX_PASTE_CHARS:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Pasted text is too long — the limit is "
                    f"{MAX_PASTE_CHARS:,} characters. Try uploading the full "
                    "document as a PDF instead."
                ),
            )
        filename = "Pasted Text"
        doc_text, page_count = pasted_text, 0
    else:
        raise HTTPException(
            status_code=400,
            detail="No contract provided — upload a PDF file or paste contract text.",
        )

    # 2. Run the hybrid risk-analysis pipeline: local pattern matching first
    #    (zero API cost), LLM (with key rotation) only for unrecognized text.
    #    Non-English `language` also translates the local findings' summaries.
    try:
        findings, provider_used = analyze_contract_text(doc_text, language)
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

    # 3. Pydantic validates the exact schema before anything reaches the client.
    return AnalyzeResponse(
        filename=filename,
        total_pages=page_count,
        language=language,
        findings=findings,
        provider_used=provider_used,
    )
