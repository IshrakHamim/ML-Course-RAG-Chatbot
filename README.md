# QueryBuddy

QueryBuddy is the ML course RAG chatbot: it answers questions **only** from a knowledge base you give it (PDF, TXT/Markdown
files and web pages), using Retrieval-Augmented Generation with Google Gemini and
PostgreSQL + pgvector. When the answer isn't in the knowledge base, it says so politely
instead of guessing.

- **Backend:** FastAPI (`backend/`), API docs at <http://localhost:8000/docs>
- **Frontend:** React + Vite + TypeScript (`frontend/`), at <http://localhost:5173>
- **Project guidelines:** [AGENTS.md](AGENTS.md)

```
React ──REST /api/v1──▶ FastAPI ──▶ rag.py ──▶ gemini.py ──▶ Gemini API
                           │           └──▶ retrieval.py ──▶ Postgres + pgvector
                           └──▶ ingestion.py (load → chunk → embed → store)
```

## Features

- Upload PDF, TXT and Markdown files, or add a web page by URL (admin only)
- Answers grounded in the retrieved chunks, with source citations (title, page or URL)
- View knowledge-base PDFs inside the app: click a PDF source under an answer to open it at
  the cited page, or use **View** on the Knowledge base page. PDFs uploaded before this
  feature need to be uploaded again once to store the file.
- Polite "not found in the knowledge base" fallback for off-topic questions, without calling
  the chat model
- Friendly replies to greetings and thanks
- Conversation memory: follow-up questions are rewritten into standalone questions
- Add or delete single documents without re-embedding everything. Identical uploads are
  detected.
- User and admin roles (JWT). Users can only see their own conversations and can delete any
  of them (the × next to each chat in the sidebar).
- Request, ingestion and chat-turn logging

## Prerequisites

| Tool | Version | macOS install |
|------|---------|---------------|
| Python | 3.11+ | `brew install python@3.12` |
| Node.js | 22+ | `brew install node@22` |
| Docker | any | Docker Desktop, or `brew install colima docker docker-compose && colima start` |

You also need a Gemini API key. A Google AI Studio key (`AIza…`, or the newer `AQ.…` format)
uses `GEMINI_USE_VERTEX=false`. A Vertex AI express-mode key uses `true`.

## Setup

```bash
# 1. Configuration
cp .env.example .env
#    Edit .env: set GEMINI_API_KEY, JWT_SECRET (32+ random characters) and
#    GEMINI_USE_VERTEX (false for Google AI Studio keys, true for Vertex AI express keys).
#    Generate a secret with: python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# 2. Database
docker compose up -d db            # or: docker-compose up -d db

# 3. Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.cli check-gemini      # must end with "All checks passed: OK"
python -m app.cli create-admin      # prompts for email and password
python -m app.cli ingest ../sample_data
uvicorn app.main:app --reload       # http://localhost:8000/docs

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

## Command-line tools

Run these from `backend/` with the virtual environment active:

| Command | What it does |
|---------|--------------|
| `python -m app.cli check-gemini` | Makes one generate call, one embed call and one batch embed call, and prints the vector length. Gives clear hints for a wrong key type, unknown model or exceeded quota. |
| `python -m app.cli create-admin [--email E]` | Creates an admin, or promotes an existing user |
| `python -m app.cli ingest PATH` | Ingests a file, or a directory (`*.pdf`, `*.txt`, `*.md`, plus URLs listed in `urls.txt`) |
| `python -m app.cli search "question"` | Shows the retrieval scores for a question, to help tune `RAG_MIN_SCORE` |
| `python -m app.cli reindex` | Re-embeds chunks after changing `GEMINI_EMBEDDING_MODEL` |

## Tuning the relevance threshold

`RAG_MIN_SCORE` (tuned to `0.59` for the sample data) decides when a question counts as "not in the knowledge base".
After ingesting the sample data, run the questions in
[docs/eval_questions.md](docs/eval_questions.md) through `python -m app.cli search`,
note the top scores, and set the threshold between the in-scope and out-of-scope groups.

## Tests and linting

```bash
# Backend: needs the Docker database. Uses a separate `ragbot_test` database and a fake
# Gemini client, so no API key or network is needed.
cd backend && ruff check . && pytest

# Frontend
cd frontend && npm run lint && npm test && npm run build
```

## Demo checklist

1. `python -m app.cli check-gemini` passes (key, models, vector length = `EMBEDDING_DIM`).
2. Ingest `sample_data/`: a PDF (`handbook.pdf`), a Markdown file and a URL (`urls.txt`).
3. Ask an in-scope question ("What is the late submission policy?") and show the sources.
   Then ask a follow-up ("Can I use grace days for the final project?").
4. Ask an out-of-scope question ("What is the capital of Australia?") and show the polite
   "not found" reply.
5. On the Knowledge base page, upload a new document and ask about it. Then delete it and ask
   again (now "not found").
6. Log in as a normal user: there's no Knowledge base link, and `GET /api/v1/documents`
   returns 403.
7. Open <http://localhost:8000/docs> and show the backend logs.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "The AI service is busy, please try again." | Check the backend log. `429 … exceeded your current quota` means the key's free-tier quota is used up: wait for it to reset, or switch to another key. Very large documents (for example a whole book) use a lot of embedding quota. `503 … high demand` is temporary on Google's side. |
| Changed `.env` but nothing is different | The backend reads `.env` only at startup (`--reload` watches code, not `.env`). Stop and restart `uvicorn`. |
| `check-gemini` reports the key was rejected, or 403 "API has not been used in project" | Flip `GEMINI_USE_VERTEX`. AI Studio keys (including newer `AQ.…` ones) need `false`. |
| `check-gemini` reports "model not found" | Check `GEMINI_CHAT_MODEL` and `GEMINI_EMBEDDING_MODEL` against the models your key can use. |
| `check-gemini` reports that batch embedding failed | Set `EMBED_BATCH_SIZE=1` in `.env`. |
| Backend exits with "Invalid configuration" | A required `.env` value is missing or invalid; the log names it. |
| `Postgres not reachable` / port 5432 in use | Start Docker (`colima start`) and `docker compose up -d db`, or stop the local Postgres using port 5432. |
| Real questions get "not found" | `RAG_MIN_SCORE` is too high; see "Tuning the relevance threshold". |
