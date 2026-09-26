# Product Requirements Document (PRD): LexLens AI

## 1. Overview
**Project Name:** LexLens AI
**One-line Summary:** A web app that scans legal contracts and flags risky clauses in plain language, so everyday people don't need to pay a lawyer for a quick review.

**Hackathon:** LexHack 2026
**Theme:** Automated contract parsers and legal workflow agents

## 2. Problem Statement
Everyday individuals and small business owners routinely sign dense, jargon-heavy legal documents (rental agreements, employment contracts, freelance SOWs) without understanding hidden risks, unfair clauses, or key financial obligations. Hiring a lawyer for a quick review costs hundreds of dollars, leaving most people completely unprotected.

## 3. Solution
LexLens AI is a web-based, automated contract parser and risk-analysis dashboard. Users drag and drop a PDF or paste raw contract text. The system parses the document in seconds, highlights high-risk or predatory clauses, categorizes clauses by topic (Termination, Liability, Payment, etc.), and provides a plain-language summary alongside actionable negotiation tips.

## 4. Target Users
- Renters signing lease agreements
- Freelancers signing SOWs/contracts
- Employees signing offer letters/employment contracts
- Small business owners without in-house legal counsel

## 5. Core Features
1. **Upload/Paste Contract** — drag-and-drop PDF or paste raw text
2. **Text Extraction** — pdfplumber/pypdf extracts clean text from PDF
3. **Hybrid Risk Detection**:
   - Fast pattern-matching against known risky-clause patterns (from CUAD/UnfairToS/MAUD reference datasets) — no API cost
   - LLM fallback (Groq/Gemini free tier, multi-key rotation) for clauses that don't match known patterns
4. **Structured Output** — every finding returned in strict JSON schema (see below)
5. **Risk Dashboard** — color-coded cards: Red (High), Yellow (Caution), Green (Safe)
6. **Plain-Language Summary** — each clause explained in simple terms
7. **Negotiation Tips** — actionable suggestion per risky clause
8. **Downloadable Risk Report** — export findings as PDF/text
9. **Disclaimer Banner** — "For informational purposes only; not official legal counsel"

## 6. JSON Response Schema
```json
{
  "clause_name": "Termination Notice",
  "risk_level": "HIGH",
  "quote": "Client may terminate with 0 days notice without compensation.",
  "plain_summary": "They can cancel on you instantly without paying you anything extra.",
  "action_step": "Request a minimum 14-day written notice requirement."
}
```

## 7. Tech Stack
| Component | Technology |
|---|---|
| Frontend | React (AI-generated via Freebuff, served as static files) |
| Backend | FastAPI (Python) |
| PDF Parsing | pdfplumber / pypdf |
| AI Inference | Groq API + Gemini API (free-tier, multi-key fallback) |
| Reference Datasets | CUAD, UnfairToS, MAUD, LEDGAR (local, used for pattern matching + prompt testing, not committed to repo) |
| Hosting | Render/Vercel (free tier) |
| Domain | Custom `.xyz` domain (LexHack sponsor perk) |

## 8. Key Technical Challenges & Solutions
**Hallucination/Legal Compliance Risk**
- Solution: Force AI to quote exact verbatim text from the uploaded document for every finding. Mandatory disclaimer banner in UI.

**Large PDFs / API Rate Limits**
- Solution: Hybrid approach — local dataset pattern matching handles most clauses instantly; only ambiguous clauses go to the LLM, minimizing API calls. Multiple API keys (Groq + Gemini, multiple accounts) provide fallback if one hits its rate limit.

**Unstructured LLM Output Breaking UI**
- Solution: Enforce strict JSON schema in every LLM prompt/response.

## 9. Out of Scope (for hackathon version)
- User accounts/login
- Persistent database storage of contracts
- RAG/vector search (direct prompt injection is sufficient at this scale)
- Multi-language support

## 10. Success Criteria (Demo)
- User uploads a real sample contract (from dataset or public template)
- App correctly flags at least 2-3 known risky clause types
- Dashboard displays clear, color-coded results within seconds
- Downloadable report works
- Live deployed link accessible on custom `.xyz` domain