"""
LexLens AI backend package.

Modules:
    config    — environment/settings loading
    schemas   — Pydantic request/response models (the clause JSON contract)
    extractor — pdfplumber-based PDF text extraction
    llm_client— Groq/Gemini calls with multi-key rotation and fallback
    analyzer  — chunking, system prompt, strict JSON parsing, orchestration
    routes    — API endpoints (POST /analyze)
    main      — FastAPI app entry point
"""
