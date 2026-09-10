# Persistent chat backend: migration review and verification

## Status

Backend routes, transactional Supabase RPC definitions, SSE stub generation, and mocked tests are implemented. No Supabase database was contacted and no migration was applied during this work. Frontend chat integration is a separate step.

The backend requires schema revision `71c9d8a6b402` before real thread creation/message persistence can work. Do not treat passing Python tests or `alembic heads` as confirmation that the database is ready.

## Files and changes

- `Backend/app/api/chat.py`: authenticated thread creation/listing/history and `POST /chat/stream`.
- `Backend/app/chat/`: typed wire models, body limits, sanitized errors, SSE orchestration.
- `Backend/app/Database/chats.py`: user-scoped reads and server-only transactional RPC calls.
- `Backend/app/Database/supabase.py`: explicitly owned HTTP clients, separate user/admin credentials, bounded HTTP timeouts. Existing helper functions remain available; the new chat/auth path uses `managed_client`.
- `Backend/app/Database/models/chat_turn.py`: turn reservations, attempt IDs, lease, and completion status.
- `Backend/app/alembic/Versions/71c9d8a6b402_persistent_stub_chat.py`: forward repair and new coordination schema/functions.

`app/Database/models/__init__.py` now registers models for Alembic. Registration exposed an invalid `Vector(dimensions=...)` constructor and an incorrect citation relationship on `DocumentChunk`; both were corrected. Message `parts` is annotated as JSON objects and non-null to match the migrated chat schema. Existing ingestion models are registered, not newly deployed by this migration; remaining model/schema drift must still be reviewed before autogeneration.

## Two distinct migration paths

### Clean disposable Supabase-compatible database

The initial revision `3c81ca3fef26` contained executable bootstrap errors. Its local source was explicitly repaired:

- Declare the ticker/year index with `op.create_index`, not `op.create_table`.
- Pass a list of column names for the message-thread index.
- Use `message_citations` consistently for table creation and policy references.
- Align user policy names and create separate source-document/chunk read policies.

These are corrections to the bootstrap script, not evidence that an already-stamped database has changed. Review this historical-file modification as part of the change set. A clean schema test needs Supabase's `auth.uid()`, `authenticated`, `anon`, and `service_role` roles, plus pgvector; an unconfigured vanilla Postgres database is not equivalent.

### Existing installation at `3c81ca3fef26`

Do not replay the initial migration, reset data, or change the Alembic stamp. After separate approval, inspect the actual schema and back up the database before considering a forward upgrade.

The new revision:

- Renames a lone legacy `messages_citations` table to `message_citations`. If both exist, it deliberately stops for manual reconciliation rather than deleting or merging data.
- Restores intended read policies and chat owner/activity/sequence indexes.
- Enables RLS on the affected tables.
- Revokes direct browser message-write privileges so clients cannot forge assistant answers.
- Adds backend-only `chat_turns` with a partial unique index allowing only one active turn per thread.
- Adds four service-role-only functions: `chat_create_thread`, `chat_accept_turn`, `chat_complete_turn`, and `chat_abandon_turn`.
- Notifies PostgREST to reload its schema cache.

Preflight must check actual columns, constraints, grants, policies, citation-table names, duplicate sequences, existing indexes, and the current Alembic revision. The forward migration assumes the existing core tables are otherwise compatible; it is not a universal repair for arbitrary manually changed schemas. Extra permissive policies must also be inspected. If an index name is occupied by a legacy table or incompatible index, stop and reconcile it explicitly.

No automatic destructive downgrade is provided. Rolling back this revision requires an explicit backup/data-retention plan. The application must be stopped or made read-only during a coordinated schema rollback; do not restore browser message-write privileges casually.

## Transaction and security design

- Backend auth verifies the Supabase token before opening a chat store. Auth outages are `503`, not forced logout `401` responses.
- Reads use the anon key plus the current user's JWT, with explicit owner filters and RLS.
- Writes use the backend service-role client and pass identity obtained from the verified token. These functions are `SECURITY INVOKER`; their EXECUTE privileges are revoked from PUBLIC, anon, and authenticated.
- Every message mutation locks the owned thread first. Owner checks happen inside the transaction, not merely before an unrestricted write.
- Creating a thread provisions the matching `public.users` row from verified identity in the same transaction.
- Accepting a turn persists the user message and reserves an assistant ID/sequence atomically. A retry with the same message UUID and text replays a completed answer without duplicate rows.
- Only the latest interrupted turn can be retried. Changed payloads, legacy untracked message IDs, active turns, and stale attempts conflict with `409`; the UI should reload history before retrying.
- Completion inserts the assistant message, marks the turn complete, and updates thread activity atomically, before a successful SSE finish event.
- Cancellation retains the user message but never marks partial assistant text complete. Attempt IDs fence off stale completions. A 90-second lease recovers from worker death; RPC row-lock waits are bounded to five seconds.
- An HTTP timeout after a successful database commit is an uncertain outcome, not proof of rollback. Reload history or retry with the same message UUID. For thread creation, inspect the thread list before retrying an uncertain create request.
- New message/assistant writes remain authoritative in the backend; clients cannot send stored assistant history as input.

Configuration defaults:

```env
SUPABASE_REQUEST_TIMEOUT_SECONDS=10
CHAT_TURN_TIMEOUT_SECONDS=30
```

The turn timeout is capped at 60 seconds, below the reservation lease. Request bodies for thread creation and streaming are bounded to 128 KiB before JSON parsing. Text input is capped at 16,000 characters. Long request-body reads time out after 10 seconds.

## Checks performed without database access

- Backend unit tests exercise real auth dependencies with mocked verification, route behavior, scoped Supabase SDK requests via HTTP MockTransport, SSE frames, persistence-before-finish, cancellation, timeout, retries, and sanitized errors.
- Backend tests replace credential environment values with placeholders and block live HTTP transports.
- Offline Alembic rendering checks the migration chain can produce SQL.
- A temporary PostgreSQL parser (`pglast`, not added to project dependencies) parsed the generated SQL and all four PL/pgSQL function bodies. Parsing verifies syntax, not execution, privileges, or locking.
- SQLAlchemy mapper registration is tested.

Repeat safe local checks from the repository root:

```text
uv run pytest tests/backend -q
```

Offline SQL rendering uses `alembic upgrade head --sql` from `Backend` with placeholder environment values. The migration test already runs this in a subprocess with test settings. Never omit `--sql` unless execution against a specifically approved database is intended.

## Still required before live acceptance

1. Review the migration changes and inspect the intended database under separate approval.
2. Run the full migration chain in a disposable Supabase-compatible database and test upgrading a representative existing schema.
3. Verify browser roles cannot execute write RPCs or insert/update assistant messages; confirm RLS blocks cross-user reads.
4. Exercise simultaneous accept calls from separate database sessions: only one active turn may succeed.
5. Exercise replay, changed-content conflicts, completion/abandon races, expired leases, stale attempt IDs, and worker-failure recovery against actual PostgreSQL.
6. Verify the reserved assistant sequence cannot collide with subsequent user turns after an interrupted turn.
7. Apply the approved migration to the intended development database only after those checks.
8. Complete frontend integration, then verify create -> send -> streamed stub -> reload history with real signed-in test users.

Database locking/RLS and live end-to-end persistence remain unverified until these gates are completed.
