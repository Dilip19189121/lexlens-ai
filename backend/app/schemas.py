"""
schemas.py — Pydantic models defining the API's request/response contracts.

Every clause finding returned by the backend MUST match `ClauseFinding`.
This is the single source of truth for the JSON schema agreed with the
frontend, and mirrors the schema in prd.md section 6.
"""

from typing import List, Literal

from pydantic import BaseModel, Field

# Allowed risk levels — the LLM is instructed to use exactly these values and
# any stray output is normalized onto the closest one downstream.
RiskLevel = Literal["HIGH", "MEDIUM", "LOW", "SAFE"]


class ClauseFinding(BaseModel):
    """One analyzed clause, exactly matching the PRD's JSON schema."""

    clause_name: str = Field(
        ...,
        description="Short human-readable name, e.g. 'Termination Notice'.",
        max_length=120,
    )
    risk_level: RiskLevel = Field(
        ...,
        description="Severity flag used by the UI for color-coding.",
    )
    quote: str = Field(
        ...,
        description="Verbatim excerpt from the uploaded document.",
        max_length=1500,
    )
    plain_summary: str = Field(
        ...,
        description="Jargon-free explanation of what the clause really means.",
        max_length=2000,
    )
    action_step: str = Field(
        ...,
        description="Concrete negotiation/next-step suggestion for the user.",
        max_length=1000,
    )


class AnalyzeResponse(BaseModel):
    """Full response body for POST /analyze."""

    filename: str = Field(..., description="Original name of the uploaded file.")
    total_pages: int = Field(..., description="Number of pages in the PDF.")
    findings: List[ClauseFinding] = Field(
        ..., description="Risk findings, worst first (HIGH → SAFE)."
    )
    provider_used: str = Field(
        ...,
        description="Which provider/key produced the result (mock/debug aid).",
    )


class ErrorResponse(BaseModel):
    """Response body for any handled API error."""

    error: str = Field(..., description="Machine-readable error code.")
    detail: str = Field(..., description="Human-readable explanation.")
