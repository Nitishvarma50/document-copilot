# Document Copilot — Resume Project Checklist

This is a portfolio project, so the goal is a clear end-to-end demo rather than a production platform. The MVP is complete when a reviewer can sign in, ask a question about the SEC filing corpus, receive a streamed answer with citations, and reopen the saved conversation.

## MVP status

- [x] Download and normalize a small SEC filing corpus.
- [x] Create the authenticated backend and database schema.
- [x] Create the authentication and conversation-history UI.
- [ ] Ingest document chunks and embeddings into Supabase.
- [ ] Retrieve relevant filing passages for a question.
- [ ] Generate a grounded answer with citations.
- [ ] Connect message sending and streaming in the frontend.
- [ ] Deploy a working demo.

---

## Already implemented

### Project setup and corpus

- [x] Configure the project with `uv`, Python 3.12+, and environment examples.
- [x] Add Python and frontend CI jobs.
- [x] Add tests, Ruff, mypy, ESLint, and production-build checks.
- [x] Configure the five-company corpus in `Data/config/corpus.json`.
- [x] Download five years of 10-K filings with SEC metadata and an idempotent manifest.
- [x] Convert all 25 selected filings to Markdown.
- [x] Extract and preserve filing tables in Markdown and JSON.

### Backend and database

- [x] Create the FastAPI application with typed settings, CORS, and `GET /health`.
- [x] Add Supabase bearer-token verification and authenticated `GET /auth/me`.
- [x] Add SQLAlchemy models and Alembic migrations for users, threads, messages, documents, chunks, citations, and chat turns.
- [x] Enable `pgvector`, vector and full-text indexes, and Row Level Security policies in the migration.
- [x] Add authenticated APIs to create/list threads and load saved messages.
- [x] Add owner-filtered chat reads and protected backend chat writes.
- [x] Add persistent user/assistant turn handling with duplicate-request and interrupted-stream protection.
- [x] Add an AI SDK-compatible text-only SSE endpoint with a clearly labelled stub response.
- [x] Add mocked tests for authentication, chat APIs, persistence behavior, and migration rendering.

### Frontend

- [x] Create the Vite, React, and TypeScript application with protected routes.
- [x] Implement Supabase email/password sign-up, sign-in, session restoration, and sign-out.
- [x] Add the authenticated HTTP client and backend identity check.
- [x] Build the responsive chat layout and conversation sidebar.
- [x] Create, list, paginate, and open conversations.
- [x] Load and render saved user and assistant messages.
- [x] Add loading, empty, retry, session-expired, and API error states.
- [x] Pass frontend ESLint and production build checks.

### Current verification

- [x] Backend and data test suite passes: 83 tests.
- [x] Frontend lint and production build pass locally.
- [x] Alembic discovers revision `71c9d8a6b402` as the current head.
- [ ] Format and lint the new ingestion files so the current Python CI job is green.
- [ ] Fix the repository-level mypy package-name error caused by the root package layout.
- [ ] Apply and test the migrations against a disposable or development Supabase database.

---

## Remaining MVP work

### 1. Finish ingestion

- [ ] Clean up and test `Data/convert_to_markdown.py` and `Backend/app/Ingest/sec_tables.py`.
- [ ] Split normalized Markdown into deterministic, section-aware chunks.
- [ ] Generate OpenAI embeddings in batches.
- [ ] Store documents and chunks in Supabase without duplicating accession numbers.
- [ ] Run one ingestion command and confirm all 25 filings have searchable chunks.

### 2. Add retrieval

Keep the first version simple: vector search plus company/year filters is enough for the demo.

- [ ] Embed the user's question.
- [ ] Query the most similar chunks with `pgvector`.
- [ ] Support optional ticker and fiscal-year filters.
- [ ] Return each passage with company, filing date, section, excerpt, and SEC URL.
- [ ] Test retrieval with 5–10 representative questions from `Docs/client_brief.md`.

### 3. Generate grounded answers

- [ ] Add one PydanticAI/OpenAI assistant that receives only retrieved passages.
- [ ] Instruct it to cite factual claims and say when the corpus lacks evidence.
- [ ] Validate that every returned citation references one of the retrieved chunks.
- [ ] Save the completed answer and citations with the conversation.
- [ ] Replace the current stub response while keeping the existing SSE contract.

### 4. Complete the chat UI

- [ ] Enable the message composer and prevent duplicate submissions.
- [ ] Send authenticated messages to `POST /chat/stream`.
- [ ] Render text while it streams and provide a stop button.
- [ ] Render citation cards with filing metadata, excerpt, and SEC link.
- [ ] Refresh the thread history after a completed response.
- [ ] Show a clear insufficient-evidence state.

### 5. Demo and deploy

- [ ] Apply migrations and ingest the corpus into the development Supabase project.
- [ ] Verify sign-up, sign-in, chat, citations, history, and sign-out end to end.
- [ ] Confirm one account cannot read another account's conversations.
- [ ] Deploy the backend and frontend.
- [ ] Add screenshots, a short architecture summary, and demo instructions to `README.md`.
- [ ] Record a short fallback demo video if the hosted services are unavailable.

---

## Optional improvements — not required for the resume MVP

- [ ] Combine vector and full-text results with Reciprocal Rank Fusion.
- [ ] Add neighboring-chunk expansion and retrieval scoring diagnostics.
- [ ] Add exact source offsets or stable page-level citations.
- [ ] Add thread rename, archive, and delete actions.
- [ ] Add request IDs, detailed usage metrics, and cost dashboards.
- [ ] Add exhaustive concurrency, cancellation, and database integration tests.
- [ ] Add a formal evaluation pipeline for every client-brief question.
- [ ] Add organization-domain restrictions and admin/user profile management.
- [ ] Add production monitoring, rate limits, backup procedures, and incident runbooks.
- [ ] Run a multi-user analyst pilot and measure time saved.
