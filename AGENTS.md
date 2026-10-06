# AGENTS.md

Guidance for AI coding agents (and humans) working on this repository.

## Project Overview

**ML Course RAG Chatbot** is an AI-powered chatbot that answers questions **only** from a custom, medium-size knowledge base using Retrieval-Augmented Generation (RAG) with the Google Gemini API.

### Core requirements (must have)

1. The chatbot is trainable on a custom, medium-size knowledge base. In practice that means document ingestion and embedding; no model fine-tuning.
2. Answers are grounded **only** in the provided knowledge base.
3. Out-of-scope questions are handled gracefully with a polite fallback, a clarification request, or a "not found in knowledge base" response. The model must never answer from its general knowledge.

### System requirements (must have)

1. A complete frontend application (chat interface for users).
2. A backend that processes queries, manages the knowledge base, and generates responses.
3. A clean, API-based architecture connecting frontend and backend.
4. The project is maintained on GitHub (see [Git Workflow](#git-workflow)).

### Additional features (good to have)

1. Intelligent knowledge retrieval (context-aware answer generation from documents).
2. Conversation memory (short-term context within a session).
3. Multiple knowledge-base formats: PDF, plain text/Markdown, web pages (URL).
4. Knowledge-base updates without full retraining (incremental add/delete of documents).
5. Authentication for users and admins.
6. API documentation.
7. Logging for the backend service.

## Tech Stack

| Layer          | Choice                                                        |
| -------------- | ------------------------------------------------------------- |
| Backend        | Python 3.11+, FastAPI, Uvicorn, Pydantic v2                   |
| LLM / Embeddings | Google Gemini via the `google-genai` SDK                    |
| Vector store   | PostgreSQL 16 + `pgvector` extension                          |
| ORM / DB       | SQLAlchemy 2.x (async) + `asyncpg`, Alembic for migrations    |
| Parsing        | `pypdf` (PDF), `httpx` + `beautifulsoup4` (web pages), plain text/Markdown |
| Auth           | JWT (`python-jose` or `pyjwt`), `passlib[bcrypt]` for password hashing |
| Frontend       | React 18 + Vite + TypeScript                                  |
| Testing        | `pytest` + `pytest-asyncio` (backend), Vitest + React Testing Library (frontend) |
| Lint / Format  | `ruff` (lint + format) for Python; ESLint + Prettier for TS   |
| Local infra    | Docker Compose (Postgres + pgvector, backend, frontend)       |

Do not introduce a new framework or major dependency without explaining why in the PR description.

## Repository Layout (target)

```
.
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── .env.example              # Template only; never real secrets
├── backend/
│   ├── pyproject.toml
│   ├── alembic/              # DB migrations
│   ├── app/
│   │   ├── main.py           # FastAPI app factory, router registration
│   │   ├── core/             # config (pydantic-settings), logging, security
│   │   ├── api/              # Routers: auth, chat, documents, health
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── ingestion/    # loaders (pdf, text, web), chunking
│   │   │   ├── embeddings.py # Gemini embedding client
│   │   │   ├── retrieval.py  # pgvector similarity search
│   │   │   ├── llm.py        # Gemini generation client
│   │   │   ├── rag.py        # orchestration: retrieve → prompt → generate
│   │   │   └── memory.py     # session conversation history
│   │   └── db/               # engine, session, base
│   └── tests/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── api/              # typed API client (single place for fetch calls)
        ├── components/       # ChatWindow, MessageBubble, SourceList, ...
        ├── pages/            # Login, Chat, Admin (knowledge base management)
        ├── hooks/
        └── types/
```

Keep this structure. If you need a new top-level module, explain why in the PR.

## Architecture

```
React (Vite) ──HTTP/JSON──▶ FastAPI ──▶ RAG service ──▶ Gemini (generate)
                               │             │
                               │             └──▶ pgvector similarity search
                               └──▶ Ingestion ──▶ chunk ──▶ Gemini (embed) ──▶ Postgres/pgvector
```

- The frontend talks to the backend **only** through the REST API under `/api/v1`. The frontend never calls Gemini directly and never holds the API key.
- All Gemini calls live in `services/embeddings.py` and `services/llm.py`. No other module imports the Gemini SDK.
- Routers stay thin: validate input, call a service, return a schema. Business logic lives in `services/`.

### RAG pipeline rules

1. **Ingestion:** load → normalize text → chunk (default ~800 tokens, ~100 token overlap; configurable) → embed → upsert to the `chunks` table along with document metadata (source, title, page/URL, document id).
2. **Retrieval:** embed the query, then do a cosine similarity search with pgvector (`top_k` default 5). Rewrite the query using recent conversation history when the question is a follow-up.
3. **Grounding / fallback:**
   - If no chunk meets the similarity threshold (configurable, e.g. `RAG_MIN_SCORE`), return the standard fallback **without calling the LLM**: *"I couldn't find that in the knowledge base. Could you rephrase or ask about a topic it covers?"*
   - The system prompt must tell the model to answer **only** from the provided context and to reply with the fallback when the context is insufficient.
   - Every answer returns the `sources` it used (document title + page/URL) so the UI can show citations.
4. **Incremental updates:** adding a document embeds only that document. Deleting a document cascades to its chunks. No full re-index is ever required. Re-uploading the same file (same content hash) is idempotent.
5. **Conversation memory:** store the last N turns per `session_id` (configurable, default 10) and include them in the prompt. Memory is short-term and scoped to a session.

### Database

- Enable `CREATE EXTENSION IF NOT EXISTS vector;` in the first Alembic migration.
- Core tables: `users`, `documents`, `chunks` (with an `embedding vector(<dim>)` column and an HNSW or IVFFlat index using `vector_cosine_ops`), `chat_sessions`, `chat_messages`.
- The embedding dimension must match the configured Gemini embedding model. Keep it in config and in the migration, not hard-coded in several places.
- All schema changes go through Alembic migrations. Never call `create_all()` in production code paths.

### Authentication

- JWT bearer tokens. Two roles: `user` (chat) and `admin` (chat + knowledge-base management + user management).
- Document upload/delete/list endpoints require `admin`.
- Passwords are hashed with bcrypt. Never log passwords or tokens.

### API conventions

- Prefix: `/api/v1`. Suggested endpoints:
  - `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
  - `POST /chat` → `{ session_id, message }` returns `{ answer, sources[], session_id }`
  - `GET /chat/sessions/{id}` (history), `DELETE /chat/sessions/{id}`
  - `POST /documents` (file upload: PDF/TXT/MD), `POST /documents/url` (web page), `GET /documents`, `DELETE /documents/{id}` (admin only)
  - `GET /health`
- Every endpoint has typed Pydantic request/response models, a `summary`, and `tags`, so the auto-generated docs at `/docs` (Swagger) and `/redoc` stay complete. These docs are the project's API documentation, so keep them accurate.
- Errors use FastAPI `HTTPException` with a consistent JSON shape: `{ "detail": "..." }`.
- Configure CORS explicitly for the frontend origin. Don't use `*` with credentials.

### Logging

- Configure logging centrally in `app/core/logging.py` using Python's `logging` module (structured/JSON format preferred). Use `logger = logging.getLogger(__name__)` in modules.
- Log request method, path, status, and latency through middleware. Log ingestion events (document id, chunk count) and RAG events (retrieved count, top score, fallback triggered).
- Never log secrets, API keys, JWTs, passwords, or full document contents.
- Don't use `print()` in backend code.

## Configuration & Secrets

- All config comes from environment variables, loaded via `pydantic-settings` in `app/core/config.py`.
- Required variables (document every new one in `.env.example`):
  ```
  GEMINI_API_KEY=
  GEMINI_CHAT_MODEL=
  GEMINI_EMBEDDING_MODEL=
  EMBEDDING_DIM=
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/ragbot
  JWT_SECRET=
  JWT_EXPIRE_MINUTES=60
  RAG_TOP_K=5
  RAG_MIN_SCORE=
  CHUNK_SIZE=800
  CHUNK_OVERLAP=100
  MEMORY_TURNS=10
  CORS_ORIGINS=http://localhost:5173
  ```
- **Never commit secrets.** `.env` must be in `.gitignore`. Never paste API keys into code, tests, docs, commit messages, or PR descriptions. If you find a secret in the repo, stop and tell the maintainer.
- Model names are configuration, not code constants.

## Development Commands

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload            # http://localhost:8000/docs
ruff check . && ruff format --check .
pytest
```

### Frontend
```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
npm run lint
npm run test
npm run build
```

### Full stack
```bash
docker compose up --build
```

If these commands change, update this section in the same PR.

## Coding Standards

### Python
- Type hints on all functions. Use Pydantic models at API boundaries.
- Use async for I/O (DB, HTTP, Gemini). Don't block the event loop. Run CPU-heavy parsing in a thread pool if needed.
- `ruff` must pass with no errors. Keep functions small and focused.
- Wrap Gemini calls with timeouts and retry with backoff on transient errors (429/5xx). Surface failures as a clean 503, not a stack trace.

### TypeScript / React
- `strict` mode on. No `any` unless justified with a comment.
- All HTTP calls go through `src/api/`. Components don't call `fetch` directly.
- Store the JWT in memory or an httpOnly cookie. Avoid `localStorage` for tokens where practical.
- The chat UI must show loading state, errors, the fallback message, and source citations.

### Tests
- Every new service function or endpoint gets tests. Mock Gemini in unit tests; tests must not need a real API key or network access.
- Cover the out-of-scope fallback path explicitly, since it's a core requirement.
- Integration tests that need Postgres should run against the Docker Compose database.

## Git Workflow

These rules are mandatory.

1. **Never commit directly to `main`.** Always create a branch first:
   - `feature/<short-description>` for new features
   - `fix/<short-description>` for bug fixes
   - `docs/<short-description>` for documentation
   - `chore/<short-description>` for tooling/config
2. Make small, focused commits with clear imperative messages, e.g. `Add PDF loader for ingestion pipeline`.
3. **Do not mention AI tools or assistants in commits or PRs.** No `Co-Authored-By` trailers, "Generated with ..." lines, or similar references to AI tooling in commit messages, PR titles, or PR descriptions.
4. When the task is done, push the branch and open a **pull request into `main`**. Merge only through the PR, never by pushing to `main` directly.
5. Before opening a PR: lint passes, tests pass, the build succeeds, `.env.example` and this file are updated if config/commands changed, and no secrets are in the diff.
6. The PR description summarizes what changed, why, and how it was tested.

## Definition of Done

- [ ] The feature meets the relevant requirement(s) listed above.
- [ ] Answers stay grounded in the knowledge base, and the fallback works for out-of-scope questions.
- [ ] Lint, type checks, and tests pass for the backend and frontend.
- [ ] API docs (`/docs`) reflect any endpoint changes.
- [ ] Logging is added for new backend flows, with no secrets logged.
- [ ] No secrets were committed.
- [ ] The work was merged to `main` through a PR from a feature branch.
