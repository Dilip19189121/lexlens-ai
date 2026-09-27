# System Architecture: LexLens AI

## 1. High-Level Architecture Diagram


```

+-----------------------------------------------------------------------+
|                             USER / BROWSER                            |
|                 (React Frontend UI - Tailored via Freebuff)           |
+-----------------------------------------------------------------------+
|
[ Upload PDF / Paste Text + language (default: English) ]
v
+-----------------------------------------------------------------------+
|                          BACKEND (FastAPI)                            |
|                                                                       |
|  1. Text Extractor (pdfplumber / pypdf)                               |
|        |                                                              |
|        v                                                              |
|  2. Hybrid Risk Engine                                                |
|     +-----------------------------------+--------------------------+  |
|     |  Pattern Matcher (Local Datasets) | LLM Fallback (Groq API)  |  |
|     |  - High-speed keyword regex       | - Structured JSON Prompt |  |
|     |  - Direct pattern detection       | - Key rotation & retry   |  |
|     +-----------------------------------+--------------------------+  |
|        |                                                              |
|        v                                                              |
|  3. JSON Formatter & Parser                                           |
+-----------------------------------------------------------------------+
|
[ Structured JSON Response ]
v
+-----------------------------------------------------------------------+
|                         RISK DASHBOARD (UI)                           |
|        - Red/Yellow/Green Flags | Plain Summary | Action Steps        |
+-----------------------------------------------------------------------+

```

---

## 2. Core Technical Components

### Frontend (User Interface)
* **Framework:** React + Tailwind CSS
* **Functionality:** Drag-and-drop document upload, real-time status indicator, interactive risk dashboard, and downloadable summary report.

### Backend (FastAPI Application)
* **Framework:** FastAPI (Python)
* **PDF Parser Module:** Uses `pdfplumber` or `pypdf` to extract clean text from multi-page documents.
* **Hybrid Processing Pipeline:**
  1. **Fast Local Matcher:** Scans text against known risky clauses from datasets (CUAD/UnfairToS) without hitting API endpoints.
  2. **LLM Fallback Module:** Passes unmatched or ambiguous clauses to the Groq API (or Gemini free tier) using strict JSON output prompts.
  3. **Translation Lane (non-English requests):** Locally pattern-matched findings carry pre-written English summaries; for non-English `language` values they are also routed through the LLM (same key-rotation chain) so `plain_summary`/`action_step` come out in the requested language. `clause_name`/`risk_level`/`quote` are re-attached from the original deterministic result — the quote is never translated, only the explanation fields. Falls back to the English text if the translation call fails.
* **Multilingual Output:** An optional `language` form field (default `"English"`) on `POST /analyze` drives a language directive in the system prompt; the response echoes the language back so the frontend knows what was used.
* **Schema Validation:** Ensures all output strictly follows the required JSON contract prior to sending it back to the client.

---

## 3. Data & API Flow

1. **Input:** User submits a legal document (PDF or plain text) plus an optional output `language` (default `"English"`) via the web client.
2. **Parsing:** FastAPI reads the document and extracts standard UTF-8 string content.
3. **Classification:**
   - Text is evaluated against pre-defined local risk rules.
   - Remaining complex sections are sent to **Groq API** with a language directive in the system prompt.
   - For non-English requests, the local findings' explanation fields are also rewritten by the **Groq API** (translation lane); quotes stay verbatim.
4. **Formatting:** Results are mapped to `clause_name`, `risk_level`, `quote`, `plain_summary`, and `action_step`, plus a top-level `language` field.
5. **Display:** The UI renders structured risk cards sorted by priority level in the requested language.

```

---

