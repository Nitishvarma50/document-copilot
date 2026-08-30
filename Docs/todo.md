# Document Copilot Implementation Checklist

This checklist turns `Docs/architecture.md` and `Docs/client_brief.md` into an implementation plan. Work from top to bottom. Do not move to the next phase until the verification items for the current phase pass.

## Definition of done

- [ ] A Driftwood analyst can sign in with a Driftwood email address.
- [ ] An analyst can ask questions about the curated SEC filing corpus from a browser.
- [ ] Answers are grounded only in retrieved filing passages.
- [ ] Every supported factual answer includes filing and page/section citations.
- [ ] The UI shows the cited source passage for verification.
- [ ] Analysts can create threads and view their own conversation history.
- [ ] The system refuses or clearly reports insufficient evidence instead of guessing.
- [ ] No user can access another user's threads or messages.
- [ ] The pilot corpus supports the ten example analyst questions in the client brief.
- [ ] Five senior analysts can use the system for a week without data loss or blocking errors.
- [ ] The pilot demonstrates at least three hours saved per analyst per week.

---

## Phase 0 — Decisions and project hygiene

- [x] Create the SEC filing downloader in `Data/download.py`.
- [x] Configure SEC requests with a descriptive `SEC_USER_AGENT`.
- [x] Download only the configured 10-K target years: 2021–2025.
- [x] Skip a company/year when that filing already exists locally.
- [x] Write a manifest containing filing metadata and local relative paths.
- [ ] Decide whether the pilot corpus contains the five companies in the brief or all ten companies in `Data/download.py`.
- [ ] Make the company list and target years a single documented configuration.
- [ ] Resolve missing filings before ingestion; the current dataset has fewer than five filings for some companies.
- [x] Keep `.env`, downloaded filings, and Python cache files out of Git.
- [x] Add setup instructions to `README.md`.
- [ ] Add a `LICENSE` or document the project's internal-only status.
- [ ] Add a basic CI workflow for formatting, type checking, tests, and build checks.

### Phase 0 verification

- [ ] `uv sync` succeeds on a clean checkout.
- [ ] The downloader fails clearly when `SEC_USER_AGENT` is not configured.
- [ ] The downloader can be run twice without redownloading existing company/year filings.
- [ ] The manifest contains the expected number of unique company/year records.

---

## Phase 1 — Backend foundation

### 1.1 Backend project structure

- [ ] Create the backend package:

  ```text
  backend/
  ├── app/
  │   ├── main.py
  │   ├── config.py
  │   ├── api/
  │   ├── auth/
  │   ├── assistant/
  │   ├── chat/
  │   ├── database/
  │   ├── grounding/
  │   ├── ingestion/
  │   └── retrieval/
  ├── alembic/
  ├── alembic.ini
  └── tests/
  ```

- [ ] Add FastAPI and Uvicorn.
- [ ] Add `pydantic-settings` for typed backend configuration.
- [ ] Add the Supabase Python client.
- [ ] Add SQLAlchemy and Alembic.
- [ ] Add `httpx` and structured logging.
- [ ] Add OpenAI and PydanticAI dependencies.
- [ ] Add a backend `pyproject.toml` or clearly define the workspace dependency layout.
- [ ] Add `backend/app/config.py` as the only backend environment-variable access point.
- [ ] Define typed settings for:
  - [ ] `SUPABASE_URL`
  - [ ] `SUPABASE_ANON_KEY`
  - [ ] `SUPABASE_SERVICE_ROLE_KEY`
  - [ ] `DATABASE_URL`
  - [ ] `OPENAI_API_KEY`
  - [ ] `ALLOWED_ORIGINS`
  - [ ] Embedding model and embedding dimensions
- [ ] Add `.env.example` entries for every backend setting.
- [ ] Add `GET /health` and verify it locally.
- [ ] Configure CORS from `ALLOWED_ORIGINS`, never `*` in production.

### 1.2 Database models and migrations

- [ ] Enable the `vector` extension in an explicit Alembic migration.
- [ ] Create the `profiles` table keyed by `auth.users.id`.
- [ ] Create the `chat_threads` table with owner and timestamps.
- [ ] Create the `chat_messages` table with ordered user/assistant messages.
- [ ] Create the `source_documents` table with:
  - [ ] Ticker and company name
  - [ ] CIK
  - [ ] Form type
  - [ ] Filing date
  - [ ] Report/fiscal year
  - [ ] Accession number
  - [ ] SEC source URL
  - [ ] Normalized Markdown content
  - [ ] Content hash for idempotent ingestion
- [ ] Create the `document_chunks` table with:
  - [ ] Document ID
  - [ ] Chunk index
  - [ ] Chunk text
  - [ ] Token count
  - [ ] Page or section metadata
  - [ ] Source offsets
  - [ ] `vector(1536)` embedding column, or the configured model dimension
  - [ ] Generated or maintained `tsvector` search column
  - [ ] JSON metadata for citation display
- [ ] Create the `message_citations` table linked to assistant messages and chunks.
- [ ] Add unique constraints for accession numbers and document content hashes.
- [ ] Add indexes for ticker, year, accession number, owner, and timestamps.
- [ ] Add an HNSW vector index after validating the chosen embedding dimension.
- [ ] Add a GIN full-text index.
- [ ] Enable Row Level Security on user-owned tables.
- [ ] Add RLS policies for profiles, threads, messages, and citations.
- [ ] Add safe read policies for source documents and chunks.
- [ ] Review every generated migration manually.
- [ ] Run migrations using a direct/session database connection, not the transaction pooler.

### 1.3 Authentication and authorization

- [ ] Configure Supabase email authentication.
- [ ] Restrict sign-in to Driftwood email addresses or an approved email domain.
- [ ] Implement bearer-token extraction in FastAPI.
- [ ] Implement Supabase JWT/user verification in `backend/app/auth/dependencies.py`.
- [ ] Expose a typed `current_user` dependency.
- [ ] Reject unauthenticated requests before retrieval or LLM work.
- [ ] Verify thread ownership on every thread, message, and citation operation.
- [ ] Add tests for missing, invalid, expired, and cross-user tokens.

### 1.4 Backend API skeleton

- [ ] Add API versioning, such as `/api/v1`.
- [ ] Add typed request and response models.
- [ ] Add thread endpoints:
  - [ ] Create thread
  - [ ] List current user's threads
  - [ ] Get one owned thread
  - [ ] Rename/archive a thread
  - [ ] Load thread messages
- [ ] Add a stub `POST /chat/stream` endpoint.
- [ ] Return clear errors for `401`, `403`, `404`, `422`, `502`, and `500` cases.
- [ ] Add request IDs and structured logs.
- [ ] Add timeout and cancellation handling for long-running LLM requests.

### Phase 1 verification

- [ ] A clean backend starts with Uvicorn.
- [ ] `/health` returns successfully.
- [ ] Alembic creates the schema from an empty database.
- [ ] RLS prevents one test user from reading another user's thread.
- [ ] The stub streaming endpoint can be consumed by a simple HTTP client.

---

## Phase 2 — Filing ingestion and citation-ready corpus

### 2.1 Normalize SEC filings

- [ ] Create `backend/app/ingestion/normalize.py`.
- [ ] Parse downloaded SEC HTML safely.
- [ ] Remove navigation, scripts, styles, and duplicate boilerplate.
- [ ] Preserve headings, tables, list structure, and filing sections.
- [ ] Normalize the filing into Markdown or structured text.
- [ ] Preserve source offsets from normalized text back to the source document.
- [ ] Preserve accession number, filing date, fiscal year, ticker, CIK, and SEC URL.
- [ ] Decide how page citations will work because raw SEC HTML does not provide reliable pages.
- [ ] If page citations are required, render filings to a stable paginated representation and store page numbers.
- [ ] Otherwise define and document a section/anchor citation format that the client approves.

### 2.2 Chunk and embed

- [ ] Create a deterministic chunking strategy based on sections and token limits.
- [ ] Avoid splitting tables or important headings from their values.
- [ ] Store neighboring-chunk relationships or reliable chunk indexes.
- [ ] Add token counting and chunk-size tests.
- [ ] Create embeddings in batches.
- [ ] Add rate limiting, retries, and resumability to embedding jobs.
- [ ] Make ingestion idempotent using accession number/content hash.
- [ ] Do not create duplicate documents or chunks on rerun.
- [ ] Store the embedding model and dimension in document metadata.
- [ ] Add a dry-run mode that reports documents/chunks without writing data.
- [ ] Add a command such as:

  ```text
  uv run python -m backend.app.ingestion.cli --input Data/downloads
  ```

### 2.3 Ingestion quality checks

- [ ] Verify every configured company/year has exactly one source document.
- [ ] Verify every document has non-empty normalized text.
- [ ] Verify chunks contain meaningful text rather than HTML boilerplate.
- [ ] Verify important sections exist where expected: Business, Risk Factors, MD&A, and financial statements.
- [ ] Verify tables are readable enough for revenue, margin, and segment questions.
- [ ] Verify every chunk has citation metadata.
- [ ] Create a small ingestion fixture for automated tests.
- [ ] Produce an ingestion report with document, chunk, token, and failure counts.

### Phase 2 verification

- [ ] The complete pilot corpus can be ingested from an empty database.
- [ ] Rerunning ingestion produces no duplicate documents or chunks.
- [ ] A chunk can be traced to a filing, section/page, and source offset.
- [ ] A human can inspect several normalized filings and confirm that tables and headings survived.

---

## Phase 3 — Retrieval

### 3.1 Semantic retrieval

- [ ] Implement query embedding generation.
- [ ] Implement bounded `pgvector` similarity search.
- [ ] Filter retrieval by available corpus metadata when the user asks about a company or year.
- [ ] Return source document and citation metadata with every result.
- [ ] Add configurable top-k limits.
- [ ] Add tests for empty, long, and company/year-filtered queries.

### 3.2 Lexical retrieval

- [ ] Implement Postgres full-text search over chunk text.
- [ ] Add language/configuration appropriate for SEC filings.
- [ ] Implement ranked keyword results.
- [ ] Add tests for exact terms such as `operating margin`, `risk factors`, and `Data Center`.

### 3.3 Hybrid retrieval and context assembly

- [ ] Implement Reciprocal Rank Fusion in `retrieval/fusion.py`.
- [ ] Deduplicate results by chunk ID.
- [ ] Fetch neighboring chunks for context without exceeding token limits.
- [ ] Preserve ranking explanations for debugging.
- [ ] Add optional metadata filters for ticker, company, form, and year.
- [ ] Implement bounded tools such as `search_filings`, `read_chunk`, and `read_surrounding_chunks`.
- [ ] Add retrieval evaluation data based on the ten client questions.
- [ ] Measure recall and inspect failed retrievals manually.

### Phase 3 verification

- [ ] Each client example question retrieves at least one relevant passage.
- [ ] Exact keyword questions work even when semantic similarity is weak.
- [ ] Multi-year comparison questions retrieve evidence from all requested years.
- [ ] Retrieval never returns chunks outside the requested company/year filters.

---

## Phase 4 — Grounded assistant and streaming backend

### 4.1 Typed agent

- [ ] Create `assistant/deps.py` with request-scoped dependencies.
- [ ] Create typed models for `Citation`, `SourcePassage`, and `GroundedAnswer`.
- [ ] Create `assistant/agent.py` using PydanticAI.
- [ ] Define the agent system instructions in a separate file.
- [ ] Require answers to use only retrieved passages.
- [ ] Require citations for factual claims.
- [ ] Require an explicit insufficient-evidence response when context is inadequate.
- [ ] Prohibit trading recommendations, stock picks, and unsupported inference.
- [ ] Keep the model from inventing page numbers, filing dates, or citations.

### 4.2 Grounding enforcement

- [ ] Implement `grounding/validator.py`.
- [ ] Verify every citation maps to a chunk retrieved for the current request.
- [ ] Verify cited passages belong to the requested corpus.
- [ ] Verify the citation contains company, filing, date, page/section, and excerpt metadata.
- [ ] Require at least one citation for supported factual answers.
- [ ] Permit zero citations only for a controlled insufficient-evidence response.
- [ ] Reject or repair invalid model output rather than returning polished unsupported text.
- [ ] Add tests for fabricated chunk IDs, wrong documents, missing citations, and unsupported claims.

### 4.3 Chat orchestration and persistence

- [ ] Implement the end-to-end turn lifecycle in `chat/orchestrator.py`.
- [ ] Load and validate the owned thread.
- [ ] Persist the user message.
- [ ] Retrieve context.
- [ ] Run the typed agent.
- [ ] Validate grounding and citations.
- [ ] Persist the assistant message and normalized citations after successful completion.
- [ ] Store model, token usage, latency, and retrieval metadata.
- [ ] Ensure failed runs do not create misleading complete assistant messages.

### 4.4 Streaming

- [ ] Implement `POST /chat/stream`.
- [ ] Accept the AI SDK UI message format.
- [ ] Translate wire messages to internal message types.
- [ ] Stream text deltas.
- [ ] Stream citation/source metadata as structured parts.
- [ ] Stream clear error events.
- [ ] Support request cancellation and timeouts.
- [ ] Test the stream with an authenticated client.

### Phase 4 verification

- [ ] A question produces a streamed answer.
- [ ] The final answer contains validated citations.
- [ ] An unsupported question produces a clear insufficient-evidence response.
- [ ] A fabricated citation cannot pass the validator.
- [ ] Completed messages and citations survive a server restart.

---

## Phase 5 — Frontend

### 5.1 Frontend foundation

- [ ] Create a Vite + React + TypeScript SPA.
- [ ] Add React Router.
- [ ] Add Tailwind CSS and shadcn/ui.
- [ ] Add `@supabase/supabase-js`.
- [ ] Add the Vercel AI SDK UI packages compatible with the installed version.
- [ ] Configure `VITE_API_BASE_URL`.
- [ ] Configure `VITE_SUPABASE_URL`.
- [ ] Configure `VITE_SUPABASE_ANON_KEY`.
- [ ] Create `src/lib/env.ts` as the only frontend environment-variable access point.
- [ ] Never expose backend service-role or OpenAI credentials.

### 5.2 Authentication UI

- [ ] Create the Supabase browser client in `src/lib/supabase.ts`.
- [ ] Implement sign-in with email/password or the approved email flow.
- [ ] Enforce the Driftwood email-domain rule in the UI and backend.
- [ ] Implement session restoration on page reload.
- [ ] Implement sign-out.
- [ ] Add loading, invalid-login, expired-session, and unauthorized states.

### 5.3 Shared API and chat state

- [ ] Create `src/lib/http.ts`.
- [ ] Inject the current Supabase access token into backend requests.
- [ ] Add request timeouts and typed API errors.
- [ ] Create `src/lib/api.ts` for threads and message history.
- [ ] Add a chat route and thread route.
- [ ] Connect `useChat`/AI SDK transport to FastAPI `/chat/stream`.
- [ ] Load stored messages when opening a thread.
- [ ] Create a new thread when starting a conversation.
- [ ] Update thread titles from the first user question or an explicit rename action.

### 5.4 Chat and citation experience

- [ ] Build the chat layout.
- [ ] Build the thread list/sidebar.
- [ ] Render user and assistant messages.
- [ ] Render streaming status and cancellation controls.
- [ ] Render Markdown safely.
- [ ] Render citations inline or beside the relevant claims.
- [ ] Render source filing, company, year, accession number, and page/section.
- [ ] Render the underlying source passage in an expandable panel.
- [ ] Link to the SEC source URL.
- [ ] Add empty states and example questions from the client brief.
- [ ] Add clear insufficient-evidence states.
- [ ] Add network, authentication, retrieval, and grounding error states.
- [ ] Prevent accidental duplicate submissions.
- [ ] Ensure the UI is usable on common laptop screen sizes.

### Phase 5 verification

- [ ] An analyst can sign in, create a thread, ask a question, and see a streamed answer.
- [ ] Refreshing the browser preserves the session and conversation history.
- [ ] Citation links and passages are readable and verifiable.
- [ ] A user cannot see another user's thread in the UI or API.
- [ ] The frontend never contains a service-role key or OpenAI key.

---

## Phase 6 — End-to-end evaluation and trust testing

- [ ] Convert the ten example questions in the client brief into an evaluation set.
- [ ] Add expected companies, years, sections, and evidence requirements for each question.
- [ ] Test single-year factual questions.
- [ ] Test multi-year comparisons.
- [ ] Test questions requiring multiple companies.
- [ ] Test financial tables and segment margins.
- [ ] Test risk-factor language changes.
- [ ] Test supplier concentration and geographic exposure questions.
- [ ] Test questions that ask for conclusions not proven by the filings.
- [ ] Confirm unsupported questions are refused rather than answered from general model knowledge.
- [ ] Manually review citation correctness for every evaluation question.
- [ ] Measure retrieval relevance, citation validity, answer support, latency, and token cost.
- [ ] Add regression tests for every discovered failure.
- [ ] Create a corpus refresh procedure for new 10-K and 10-Q filings.

### Trust and security review

- [ ] Confirm all answers are generated only from retrieved corpus passages.
- [ ] Confirm every factual claim has a citation or is explicitly qualified.
- [ ] Confirm source excerpts exactly match stored source text.
- [ ] Confirm page/section metadata is stable after re-ingestion.
- [ ] Confirm RLS and backend ownership checks are both active.
- [ ] Confirm secrets are absent from Git, browser bundles, logs, and error responses.
- [ ] Confirm rate limits and request size limits are configured.
- [ ] Confirm prompt injection in filing text cannot override system instructions.
- [ ] Confirm HTML parsing sanitizes untrusted document content.

---

## Phase 7 — Deployment and pilot

### Railway and Supabase

- [ ] Create the Supabase project.
- [ ] Configure Supabase Auth and the approved Driftwood email policy.
- [ ] Apply Alembic migrations to Supabase Postgres.
- [ ] Verify `pgvector`, full-text indexes, and RLS policies in the deployed database.
- [ ] Create the Railway backend service.
- [ ] Configure backend secrets in Railway.
- [ ] Create the Railway frontend service.
- [ ] Configure frontend build and runtime variables.
- [ ] Configure production CORS for the frontend origin.
- [ ] Configure health checks and restart behavior.
- [ ] Add production logging and error monitoring.
- [ ] Document the deployment and rollback process.

### Pilot readiness

- [ ] Ingest the final pilot corpus into the deployed database.
- [ ] Run the full evaluation set against production.
- [ ] Invite five senior analysts.
- [ ] Provide a short usage guide with example questions.
- [ ] Capture feedback on answer correctness, citation usefulness, latency, and time saved.
- [ ] Track failed questions and add them to regression tests.
- [ ] Measure whether the pilot saves at least three hours per analyst per week.
- [ ] Fix blocking trust, auth, and data-quality issues before firm-wide rollout.
- [ ] Prepare an operations runbook for corpus refreshes, incidents, and database recovery.
