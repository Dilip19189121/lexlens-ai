# tasks.md — LexLens AI

## Phase 1: Backend Setup
- [x] Set up FastAPI project structure in `/backend`
- [x] Create PDF/text upload endpoint (PDF upload done; raw-text paste arrives with the frontend)
- [x] Integrate pdfplumber/pypdf for text extraction
- [x] Get Groq API key(s) (2+ accounts for fallback) — *user action: pasted into `backend/.env`; verified live (2 keys)*
- [x] Get Gemini API key — *user action: pasted into `backend/.env`; verified configured*
- [x] Build multi-key fallback logic (try Groq → Gemini → next key on rate limit)
- [x] Write system prompt enforcing strict JSON schema output
- [x] Test structured JSON output with sample clause text (Postman/curl) — smoke test passes offline (mock) AND live (`--live`): real Groq call, 7 schema-valid findings

## Phase 2: Hybrid Risk Detection
- [x] Build local keyword/pattern matcher using CUAD/UnfairToS/MAUD reference data — `backend/app/pattern_matcher.py`: 27 rules (clause names/categories from CUAD's 41-category taxonomy, aggravator vocabulary from UnfairToS, no-shop/assignment constructions from MAUD), punctuation/whitespace-tolerant matching
- [x] Route matched clauses → instant local response (no API call) — matched sentence spans are excluded from the LLM lane; sample contract: 7 risky clauses caught locally
- [x] Route unmatched clauses → LLM API call — only uncovered text is chunked and sent (sample: 215/988 chars); `provider_used` reports e.g. `local-patterns+groq:key#1`
- [x] Test full pipeline: upload → extract → detect → JSON output — offline smoke suite (18 checks) + live e2e: 12 findings, PRD schema, sorted HIGH→SAFE, single Groq request

## Phase 2.5: Multilingual Output
- [x] Add optional `language` form field to POST /analyze (default "English"; accepts e.g. "Telugu", "Hindi") — echoed back in the JSON response for the frontend
- [x] Language-aware system prompt: `plain_summary`/`action_step` written in the requested language; `clause_name`/`quote` kept in the source language (quote stays verbatim, never translated)
- [x] Route locally pattern-matched findings through the LLM for non-English requests (translation lane, same key-rotation chain) so hardcoded English summaries don't leak into the response; graceful English fallback if translation fails; `provider_used` gains a `+translate(<provider>)` suffix (e.g. `local-patterns+groq:key#1+translate(groq:key#1)`)
- [x] Smoke tests extended: offline (24 checks) + live Telugu run — `plain_summary`/`action_step` return in Telugu (U+0C00–U+0C7F) while `quote` contains zero Telugu codepoints (verbatim English preserved); translation lane reported in `provider_used`

## Phase 3: Frontend
- [x] Generate UI via Freebuff/AI tool: upload dropzone + dashboard layout
- [x] Apply design skill (Taste/Awesome Design) for polish — Impeccable skill pass: visible keyboard focus, themed scrollbars, honest stats (27 rules / 3 languages / 0 retention), dot-icons instead of emoji, mobile nav drawer, tabular numerals, 10px legal text bumped to 12px
- [x] Build color-coded risk cards (Red/High, Yellow/Caution, Green/Safe) — cards render dynamically from findings; MEDIUM/LOW both map to Caution-yellow
- [x] Display clause_name, quote, plain_summary, action_step per card
- [x] Add disclaimer banner ("informational purposes only") — top notice bar + report footer
- [x] Connect frontend to backend API — real fetch to POST /analyze (PDF upload *or* pasted text + language), real progress bar, dynamic summary counts/filters/audit title, SpeechSynthesis audio (en-US/te-IN/hi-IN), clean error banner for 400/422/502/503/network, drag-and-drop upload, text-report download, language switch re-runs the same document
- [x] Serve frontend as static files from FastAPI (single deployable app) — GET / serves backend/frontend/index.html, /static mounts the folder; one uvicorn process serves UI + API. The frontend lives INSIDE backend/ (backend/frontend/) so the deploy root can be set to backend/ on Railway/Render and the whole app deploys as one folder
- [x] Playwright e2e pass (scripts/e2e/e2e_test.js): 27/27 checks — real PDF upload → loading → 12 real findings → filters → Telugu re-run (Telugu summaries, verbatim quotes) → audio speaks → paste flow → download → mobile viewport (no overflow, menu works) — screenshots in scripts/e2e/screenshots/
- [x] Bugfix: header language selector was decorative (no id, not wired) — selecting Telugu there still sent `language=English`. Both selects are now synced bidirectionally and either triggers a re-run; `/` serves with `Cache-Control: no-store`; regression test scripts/e2e/verify_lang_fix.js (8/8: header path, workspace path, select sync, Telugu + Devanagari rendering)

## Phase 4: Extra Features & Polish
- [ ] Add "Download Risk Report" export button
- [ ] Test with 2–3 real sample contracts (from datasets/templates)
- [ ] Fix UI bugs / responsive check
- [ ] (Optional) Playwright test pass for visual bugs

## Phase 5: Deployment
- [ ] Push final code to GitHub
- [ ] Deploy backend+frontend (Render/Vercel free tier)
- [ ] Register/point free `.xyz` domain (code LXH26) to deployed app
- [ ] Verify live link works end-to-end

## Phase 6: Submission
- [ ] Record 2–3 min demo video (walkthrough of a contract scan)
- [ ] Write Devpost submission: Project Name, Summary, Problem & Solution
- [ ] List full tech stack (mention sponsor APIs used, if any)
- [ ] Add GitHub repo link + live demo link
- [ ] Final review and submit before deadline