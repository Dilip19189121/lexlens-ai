# LexLens AI

## Overview
LexLens AI is a web-based contract analyzer that helps everyday individuals and small business owners understand risky or unfair clauses in legal documents (rental agreements, employment contracts, freelance SOWs) without paying for expensive legal review.

## Problem & Solution
People sign dense legal contracts without understanding hidden risks. Hiring a lawyer for a quick review is expensive. LexLens AI parses uploaded contracts, flags high-risk clauses in plain language, and gives actionable negotiation tips — instantly and for free.

## Tech Stack
- Backend: FastAPI (Python)
- Frontend: React (served as static files from FastAPI)
- AI: Groq API + Gemini API (free-tier, multi-key fallback for reliability)
- PDF parsing: pdfplumber / pypdf
- Reference datasets (for testing/prompt validation): CUAD, UnfairToS

## Why Multiple API Keys?
Free-tier LLM APIs have rate limits (requests per minute). To keep the app responsive during demo and normal use, the backend rotates between multiple provider keys and automatically falls back to the next one if a limit is hit. Actual key values are stored in environment variables, not committed to this repo.

## Folder Structure

lexlens-ai/
├── backend/ → FastAPI app, routes, LLM logic, PDF parsing
├── frontend/ → React UI (upload box, risk cards, dashboard)
├── README.md


## Core Features
1. Upload PDF or paste contract text
2. Extract raw text (pdfplumber)
3. Match against known risky-clause patterns first (fast, no API cost)
4. For unmatched/complex clauses, send to LLM (Groq/Gemini) with structured JSON prompt
5. Return risk-flagged clauses (HIGH / MEDIUM / LOW)
6. Display as color-coded cards (Red / Yellow / Green)
7. Download risk report

## JSON Response Schema
```json
{
  "clause_name": "Termination Notice",
  "risk_level": "HIGH",
  "quote": "Client may terminate with 0 days notice without compensation.",
  "plain_summary": "They can cancel on you instantly without paying you anything extra.",
  "action_step": "Request a minimum 14-day written notice requirement."
}
```

## Environment Variables (.env — not committed)
GROQ_API_KEY_1=
GROQ_API_KEY_2=
GEMINI_API_KEY=


## Disclaimer
This tool is for informational purposes only and does not constitute legal advice.
