# LexLens AI

## Overview
[Paste your problem statement + solution summary]

## Tech Stack
- Backend: FastAPI (Python)
- Frontend: React (served as static files from FastAPI)
- AI: Groq / Gemini (free tier, multi-key fallback)
- PDF parsing: pdfplumber

## Folder Structure
- /backend - FastAPI app, routes, LLM logic
- /frontend - React build (pasted from Lovable/v0)

## Core Features
1. Upload PDF/paste text
2. Extract text (pdfplumber)
3. Send to LLM with structured JSON prompt
4. Return risk-flagged clauses (HIGH/MEDIUM/LOW)
5. Display as color-coded cards

## JSON Response Schema
[Paste your clause_name/risk_level/quote/plain_summary/action_step structure]

## Environment Variables
- GROQ_API_KEY_1
- GROQ_API_KEY_2
- GEMINI_API_KEY
