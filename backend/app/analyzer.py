"""
analyzer.py — Hybrid risk-analysis pipeline.

Responsibilities:
  1. Route each paragraph through the LOCAL pattern matcher first — known
     risky clauses (from the CUAD/UnfairToS/MAUD-derived rulebook) return
     instantly with zero API cost.
  2. Batch only UNRECOGNIZED paragraphs into LLM-sized chunks (with overlap
     so clauses split across a boundary aren't lost) and call the LLM with
     multi-key rotation.
  3. Hold THE system prompt that forces strict JSON schema output, with a
     language directive so plain_summary/action_step can be produced in the
     requested output language while quotes stay verbatim.
  4. Parse/validate the model's response into `ClauseFinding` objects —
     salvaging malformed JSON if the model wraps it in prose or fences.
"""

import json
import logging
import re
from typing import List

from . import llm_client, pattern_matcher
from .config import CHUNK_OVERLAP_CHARS, MAX_CHUNK_CHARS
from .schemas import ClauseFinding

# ── The system prompt ───────────────────────────────────────────────────────
# This is the single most important string in the app: it forces the model to
# return ONLY a JSON array matching the PRD schema, and to quote verbatim
# text (the anti-hallucination requirement from prd.md section 8).
SYSTEM_PROMPT = """You are a cautious legal-document analyst for everyday people \
(renters, freelancers, employees, small business owners). You review contract \
text and flag clauses that could hurt the non-drafting party.

Return ONLY a JSON array — no markdown fences, no explanations, no extra text. \
Each element MUST have exactly these five string fields:
  - "clause_name": short human-readable name (e.g. "Termination Notice")
  - "risk_level": one of "HIGH", "MEDIUM", "LOW", "SAFE"
  - "quote": an EXACT verbatim excerpt copied character-for-character from the \
provided text (never paraphrase or invent text)
  - "plain_summary": what the clause really means in simple language
  - "action_step": one concrete thing the reader can do about it

Rules:
  - Analyze every distinct clause or section in the provided text.
  - Flag as HIGH: instant termination, unilateral changes, heavy liability, \
auto-renewal traps, broad IP assignment, penalties, non-competes.
  - Flag as LOW or SAFE only for genuinely ordinary, balanced clauses.
  - If the text contains no analyzable clauses, return [].

Example output:
[{"clause_name": "Termination Notice", "risk_level": "HIGH", "quote": "Client \
may terminate with 0 days notice without compensation.", "plain_summary": "They \
can cancel on you instantly without paying you anything extra.", "action_step": \
"Request a minimum 14-day written notice requirement."}]"""

logger = logging.getLogger("lexlens")

# ── Multilingual support ──────────────────────────────────────────────

# Default output language. Requests may pass any language name (English,
# Telugu, Hindi, ...); English keeps the zero-extra-cost local lane.
DEFAULT_LANGUAGE = "English"


def build_system_prompt(language: str = DEFAULT_LANGUAGE) -> str:
    """Return the system prompt with a language directive for the output.

    plain_summary and action_step follow the requested language; clause_name
    and quote stay in the source document's language — the quote must remain
    verbatim (the anti-hallucination rule, prd.md section 8) and clause_name
    is a stable UI label. English gets the base prompt unchanged.
    """
    if not language or language == DEFAULT_LANGUAGE:
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + (
        "\n\nLanguage requirement: Write the plain_summary and action_step "
        f"fields in {language}. Keep the clause_name and quote fields in "
        "their original language (do not translate the quote — it must "
        "remain verbatim from the source document)."
    )


def _translate_system_prompt(language: str) -> str:
    """System prompt for the local-findings translation lane.

    The pattern matcher's plain_summary/action_step strings are pre-written
    in English; when the user requests another language, these findings are
    routed through the LLM too (same key-rotation chain) so the WHOLE
    response speaks one language.
    """
    return (
        "You are a translator for a legal-risk report aimed at everyday "
        "people. You will receive a JSON array of clause findings. Return "
        "ONLY a JSON array — no markdown fences, no explanations — with the "
        "same elements in the same order and the same number of elements.\n"
        "For each element:\n"
        '  - "quote": keep EXACTLY as given — it is verbatim source text and '
        "must never be translated or altered.\n"
        '  - "clause_name": keep EXACTLY as given (stable English UI label).\n'
        '  - "risk_level": keep EXACTLY as given.\n'
        f'  - "plain_summary" and "action_step": rewrite in {language}, '
        "preserving the meaning in simple, natural phrasing.\n"
        "Output only the JSON array."
    )


def _translate_findings(findings: List[ClauseFinding], language: str) -> tuple:
    """Rewrite locally-matched findings' plain_summary/action_step in `language`.

    Sends the findings (as a JSON payload) through the same key-rotation LLM
    chain. clause_name, risk_level, and quote are re-attached from the
    ORIGINAL findings, so no model output can corrupt the verbatim-quote
    guarantee. Raises ProviderError / ValueError like the main lane —
    callers decide whether to fall back to the English text.
    """
    payload = json.dumps([f.model_dump() for f in findings])
    raw, provider = llm_client.call_llm(_translate_system_prompt(language), payload)
    translated = parse_findings(raw)
    if len(translated) != len(findings):
        raise ValueError(
            f"translation returned {len(translated)} findings, "
            f"expected {len(findings)}"
        )
    merged = [
        ClauseFinding(
            clause_name=f.clause_name,
            risk_level=f.risk_level,
            quote=f.quote,  # verbatim from the document, never the model's
            plain_summary=t.plain_summary or f.plain_summary,
            action_step=t.action_step or f.action_step,
        )
        for f, t in zip(findings, translated)
    ]
    return merged, provider

# ── Chunking ────────────────────────────────────────────────────────────────

def chunk_text(text: str) -> List[str]:
    """Split contract text into slices that fit the LLM context comfortably.

    Chunks overlap by CHUNK_OVERLAP_CHARS so a clause cut in half at a chunk
    boundary is still fully visible to the model in at least one chunk.
    Paragraph breaks are preferred as cut points to avoid mid-sentence cuts.
    """
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + MAX_CHUNK_CHARS, len(text))
        if end < len(text):
            # Try to cut at the last paragraph break in the window.
            break_at = text.rfind("\n\n", start, end)
            if break_at == -1:
                # Fall back to a single newline, then a sentence end.
                break_at = text.rfind("\n", start, end)
            if break_at > start + MAX_CHUNK_CHARS // 2:
                end = break_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        # Step back the overlap so the next chunk re-reads the tail of this one.
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
    return chunks


# ── Response parsing ────────────────────────────────────────────────────────

def _extract_json_array(raw: str) -> str:
    """Isolate the JSON array inside a model response.

    Models sometimes wrap JSON in ```json fences or prepend prose despite the
    system prompt. This finds the outermost [...] region and returns it.
    Raises ValueError if no plausible array is present.
    """
    raw = raw.strip()
    # Drop ```json ... ``` / ``` ... ``` fences if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON array found in model output")
    return raw[start : end + 1]


def _normalize_risk_level(value: str) -> str:
    """Map stray model output onto the four allowed risk levels.

    Handles 'CRITICAL' → HIGH, 'caution'/'warning' → MEDIUM, etc., and
    defaults to MEDIUM (visible but not alarming) when unrecognized.
    """
    v = str(value).strip().upper()
    if v in ("HIGH", "MEDIUM", "LOW", "SAFE"):
        return v
    if v in ("CRITICAL", "SEVERE", "EXTREME", "RED"):
        return "HIGH"
    if v in ("CAUTION", "WARNING", "MODERATE", "YELLOW", "AMBER"):
        return "MEDIUM"
    if v in ("MINIMAL", "NONE", "GREEN", "OK", "OKAY"):
        return "SAFE"
    return "MEDIUM"


def _clean_finding(item: dict) -> ClauseFinding:
    """Coerce one model-produced dict into a valid ClauseFinding.

    Fills missing fields with safe defaults and normalizes the risk level so
    one sloppy element never crashes the whole request.
    """
    get = lambda key: str(item.get(key) or "").strip()
    return ClauseFinding(
        clause_name=get("clause_name") or "Unnamed Clause",
        risk_level=_normalize_risk_level(item.get("risk_level", "MEDIUM")),
        quote=get("quote"),
        plain_summary=get("plain_summary"),
        action_step=get("action_step"),
    )


def parse_findings(raw: str) -> List[ClauseFinding]:
    """Turn raw LLM text into validated ClauseFinding objects.

    Attempts strict JSON parsing first, then the fence/prose-tolerant salvage
    path. Raises ValueError if no usable JSON can be recovered.
    """
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        items = json.loads(_extract_json_array(raw))

    if not isinstance(items, list):
        raise ValueError("Model output is valid JSON but not an array")
    return [_clean_finding(item) for item in items if isinstance(item, dict)]


# ── Orchestration ───────────────────────────────────────────────────────────

def _norm_quote(quote: str) -> str:
    """Collapse whitespace and lowercase a quote for comparison."""
    return re.sub(r"\s+", " ", quote.lower()).strip()


def _same_quote_region(a: str, b: str) -> bool:
    """Heuristic: do two quotes point at the same document text?

    The LLM and the pattern matcher may quote the same clause with slightly
    different windows (different start/end, '2. TERMINATION.' prefix, etc.).
    Comparing normalized quotes as substrings of each other catches that.
    """
    na, nb = _norm_quote(a), _norm_quote(b)
    probe_a, probe_b = na[:100], nb[:100]
    return bool(probe_a) and bool(probe_b) and (probe_a in nb or probe_b in na)


def analyze_contract_text(text: str, language: str = DEFAULT_LANGUAGE) -> tuple:
    """Hybrid analysis of the full contract text: (findings, provider_used).

    Pipeline (prd.md section 5, "Hybrid Risk Detection"):
      1. Split into paragraphs; run the local pattern matcher on each.
         Matched paragraphs yield findings INSTANTLY and never hit the API.
      2. Paragraphs the matcher didn't recognize are joined and chunked
         (with overlap) for the LLM, which runs with multi-key rotation.
      3. Merge (local findings first, so dedupe prefers the deterministic
         result), drop quotes pointing at the same clause text, and sort
         HIGH → SAFE so the UI renders the worst risks first.

    Multilingual: for non-English requests the locally-matched findings are
    additionally routed through the LLM (translation lane) so their
    plain_summary/action_step come out in the requested language — keeping
    the whole response consistent. Quotes stay verbatim regardless.

    provider_used is a debug aid: 'local-patterns' when the matcher caught
    everything, the LLM provider label when nothing matched, or
    'local-patterns+<provider>' for the mixed case. In non-English runs a
    '+translate' suffix records that the local findings were also LLM-
    processed (e.g. 'local-patterns+groq:key#1+translate').

    Raises:
        llm_client.ProviderError: if every provider/key is exhausted.
        ValueError: if a provider response can't be parsed as the schema.
    """
    # ── 1. Fast local lane ──
    # Known risky clauses are caught here instantly — zero API cost. Match
    # spans are widened to sentence bounds, and only the text they DON'T
    # cover gets passed to the LLM lane.
    local_findings, spans = pattern_matcher.match_with_spans(text)
    unmatched_text = pattern_matcher.uncovered_text(text, spans)

    # ── 2. LLM lane for unrecognized text only ──
    language = (language or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    system_prompt = build_system_prompt(language)
    needs_translation = language != DEFAULT_LANGUAGE and bool(local_findings)

    llm_findings: List[ClauseFinding] = []
    provider_used = "local-patterns"
    if unmatched_text:
        for chunk in chunk_text(unmatched_text):
            raw, provider = llm_client.call_llm(system_prompt, chunk)
            provider_used = provider
            llm_findings.extend(parse_findings(raw))
        if local_findings:
            provider_used = f"local-patterns+{provider_used}"

    # ── 2b. Translation lane for local findings (non-English only) ──
    # The rulebook's plain_summary/action_step strings are pre-written in
    # English; route them through the LLM too so the whole response speaks
    # one language. On failure, keep the English originals (the verbatim
    # quotes are unaffected either way) rather than failing the request.
    if needs_translation:
        try:
            local_findings, translate_provider = _translate_findings(
                local_findings, language
            )
            provider_used += f"+translate({translate_provider})"
        except (llm_client.ProviderError, ValueError) as exc:
            logger.warning(
                "Translation of local findings to %s failed; falling back to "
                "English summaries: %s",
                language,
                exc,
            )

    # ── 3. Merge, dedupe, sort ──
    all_findings = local_findings + llm_findings
    unique: List[ClauseFinding] = []
    for f in all_findings:
        if any(
            f.clause_name.lower() == g.clause_name.lower()
            and _same_quote_region(f.quote, g.quote)
            for g in unique
        ):
            continue
        if any(_same_quote_region(f.quote, g.quote) for g in unique):
            # Same text quoted under different names — keep the earlier one
            # (local pattern findings are inserted first for this reason).
            continue
        unique.append(f)

    # Worst first: HIGH → MEDIUM → LOW → SAFE.
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "SAFE": 3}
    unique.sort(key=lambda f: order.get(f.risk_level, 4))
    return unique, provider_used
