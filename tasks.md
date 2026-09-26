# tasks.md — LexLens AI

## Phase 1: Backend Setup
- [x] Set up FastAPI project structure in `/backend`
- [x] Create PDF/text upload endpoint (PDF upload done; raw-text paste arrives with the frontend)
- [x] Integrate pdfplumber/pypdf for text extraction
- [ ] Get Groq API key(s) (2+ accounts for fallback) — *user action: paste into `backend/.env`*
- [ ] Get Gemini API key — *user action: paste into `backend/.env`*
- [x] Build multi-key fallback logic (try Groq → Gemini → next key on rate limit)
- [x] Write system prompt enforcing strict JSON schema output
- [x] Test structured JSON output with sample clause text (Postman/curl) — smoke test + live curl in mock mode; retest with real keys once added

## Phase 2: Hybrid Risk Detection
- [ ] Build local keyword/pattern matcher using CUAD/UnfairToS/MAUD reference data
- [ ] Route matched clauses → instant local response (no API call)
- [ ] Route unmatched clauses → LLM API call
- [ ] Test full pipeline: upload → extract → detect → JSON output

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