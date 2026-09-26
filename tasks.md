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

## Phase 3: Frontend
- [ ] Generate UI via Freebuff/AI tool: upload dropzone + dashboard layout
- [ ] Apply design skill (Taste/Awesome Design) for polish
- [ ] Build color-coded risk cards (Red/High, Yellow/Caution, Green/Safe)
- [ ] Display clause_name, quote, plain_summary, action_step per card
- [ ] Add disclaimer banner ("informational purposes only")
- [ ] Connect frontend to backend API
- [ ] Serve frontend as static files from FastAPI (single deployable app)

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