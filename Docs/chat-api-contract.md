# Persistent stub chat: implementation contract

Status: backend implementation and schema preparation are complete. Frontend conversation/history loading, SDK streaming, and history/sidebar reconciliation are implemented and locally checked with mocked services, including browser smoke checks. Database execution and live end-to-end acceptance remain pending. See `Frontend/README.md` for verification limits and `Docs/chat-backend-migrations.md` for required database gates.
This contract scopes the approval-gated backend and frontend steps.

## Scope

- Keep the Vite SPA, Supabase email/password authentication, and FastAPI backend.
- Create/list owned threads, submit a text message, stream an explicitly labelled stub response, and reload persisted history.
- No retrieval, embeddings, LLM calls, citations, attachments, tools, message editing, regeneration, or resumable streams in this slice.
- Store history in Supabase Postgres, not browser storage or process memory.
- Keep tests under root `tests/backend/`; frontend tests remain deferred.

## Review findings and prerequisites

- Existing frontend auth, route protection, HTTP client, and `/auth/me` can be reused.
- `Backend/app/auth/dependencies.py` must import `AuthApiError` from `supabase_auth.errors`. Step 1 restores this and `Annotated` dependencies while preserving the local null-response guard.
- Existing tables are `users`, `chat_threads`, and `chat_messages`, not the target architecture's `profiles` table. Use existing names for this slice; do not introduce a parallel user table.
- `chat_threads.user_id` references `users.id`, but no signup trigger or application-user provisioning exists. Derive the application-user ID and email only from verified Supabase identity; never generate a different user ID.
- The migration requires `users.display_name`, thread title, message `parts`, and message `sequence`; inserts must supply compatible values.
- `chat_messages.parts` is JSONB, but its ORM annotation is `list[str]`. Align the annotation with structured text-part objects when implementing persistence.
- Existing message RLS policies omit INSERT. Do not assume the untracked user-scoped Supabase helper can write messages.
- The initial migration has clean-bootstrap defects: an index is declared using `op.create_table`, citations are created as `messages_citations` but policies reference `message_citations`, and policy creation/drop names are inconsistent. Source-document read policy coverage is also inconsistent.
- Migration discovery in CI does not execute migrations. Earlier database revision reports do not establish that deployed tables match these files.

Database implementation must reconcile the intended schema with the existing migration chain. Preserve existing data; do not reset a database or silently rewrite applied migration history. Schema inspection and live migration execution require separate approval. Any local bootstrap correction and forward repair migration must be reviewed and tested before claiming clean-database readiness.

## SDK compatibility

Verified against npm package metadata and published package source:

- `ai@7.0.94` requires Node.js >=22.
- `@ai-sdk/react@4.0.97` depends on `ai@7.0.94` and accepts the project's React 19.2 version.
- `useChat` supports `id`, initial `messages`, `generateId`, `transport`, `sendMessage`, `stop`, `status`, and completion/error callbacks.
- `DefaultChatTransport` supports asynchronous headers and `prepareSendMessagesRequest`.
- The default transport sends `id`, full `messages`, `trigger`, and optional `messageId`. Customize the request explicitly rather than assume it sends `threadId`.
- Use `generateId: () => crypto.randomUUID()` to match the database UUID message IDs.
- Installed during the approved frontend streaming step with `npm install --save-exact ai@7.0.94 @ai-sdk/react@4.0.97`; both versions are pinned in `Frontend/package.json` and `package-lock.json`.

References:

- https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
- https://ai-sdk.dev/docs/ai-sdk-ui/transport
- Published sources: `ai/src/ui/http-chat-transport.ts`, `ai/src/ui/default-chat-transport.ts`, `ai/src/ui-message-stream/ui-message-chunks.ts`, and `@ai-sdk/react/src/use-chat.ts` at the versions above.

## Frontend routes

| Route | Behavior |
| --- | --- |
| `/login` | Existing public sign-in page |
| `/signup` | Existing public signup page |
| `/` | Redirect to `/chat` |
| `/chat` | Protected thread sidebar and new-conversation empty state |
| `/chat/:threadId` | Protected sidebar and selected thread/history/composer |

New chat creates a server thread before navigating to its route. Do not create threads during render or a mount effect. Disable duplicate create/send actions while pending.

Load initial history before mounting the thread's `useChat` component. Key that component by thread ID; abort in-flight history loads and stop the old stream on route change/unmount. Never briefly show another thread's messages. Refresh the sidebar and authoritative history after successful completion; reconcile history after cancellation/error without replacing a live stream.

## REST API

All endpoints require `Authorization: Bearer <Supabase access token>`. UUIDs are strings and timestamps are UTC ISO 8601 strings. API properties use camelCase; database columns retain snake_case.

### POST /threads

Request: `{ "title": "New chat" }`, with title optional, nonblank, and at most 225 characters.

Response: `201 Created`, with the thread object:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "title": "New chat",
  "createdAt": "2026-01-01T00:00:00Z",
  "updatedAt": "2026-01-01T00:00:00Z"
}
```

Derive ownership from the verified identity. Bootstrap the application-user record server-side if absent. Default titles can be replaced by a bounded excerpt of the first accepted user message; no LLM title generation.

### GET /threads?limit=50&cursor=...

Response: `{ "threads": [<thread>], "nextCursor": null }`.

Return only the caller's threads, ordered by `updated_at DESC, id DESC`. Default limit 50, maximum 100. Use a validated opaque cursor for pagination and deduplicate sidebar results by ID when refreshing.

### GET /threads/{threadId}/messages?limit=100&afterSequence=0

Response:

```json
{
  "thread": {
    "id": "11111111-1111-4111-8111-111111111111",
    "title": "Example question",
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:01Z"
  },
  "messages": [
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "role": "user",
      "parts": [{ "type": "text", "text": "Example question" }],
      "metadata": { "sequence": 1, "createdAt": "2026-01-01T00:00:01Z" }
    }
  ],
  "nextAfterSequence": null
}
```

Return messages in ascending sequence order (starting at 1), with stable persisted IDs and AI SDK-compatible parts. Default limit 100, maximum 500. Fetch remaining pages before initializing the full history in this first UI. Missing and non-owned threads both return `404` to avoid revealing another user's resource existence; this is a deliberate refinement of the broader architecture's `403` example.

## POST /chat/stream

The transport sends exactly the new user message, not a client-authoritative history:

```json
{
  "threadId": "11111111-1111-4111-8111-111111111111",
  "trigger": "submit-message",
  "messages": [
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "role": "user",
      "parts": [{ "type": "text", "text": "Example question" }]
    }
  ]
}
```

`prepareSendMessagesRequest` selects the newest user message and maps the hook's chat ID to `threadId`. Reject unsupported triggers, roles, parts, and extra identity fields. Accept exactly one text part, nonblank and at most 16,000 characters, with a bounded overall body size. The backend loads history itself if needed; it must not persist browser-supplied assistant messages.

Read the current session token per request, not once at component creation. Streaming uses the transport's fetch path; do not pass the SSE response to the existing JSON/text-parsing HTTP helper. A shared authenticated raw-fetch layer can preserve typed HTTP errors and token handling without consuming the stream. Propagate the SDK abort signal.

### Response protocol

Validate auth, input, ownership, and turn acceptance before beginning the `200` response. Headers:

```http
Content-Type: text/event-stream
Cache-Control: no-cache, no-transform
x-vercel-ai-ui-message-stream: v1
X-Accel-Buffering: no
```

Emit UTF-8 SSE frames separated by a blank line. Use JSON serialization, not interpolated user text. Minimal successful response:

```text
data: {"type":"start","messageId":"33333333-3333-4333-8333-333333333333"}

data: {"type":"text-start","id":"text-1"}

data: {"type":"text-delta","id":"text-1","delta":"Stub response: "}

data: {"type":"text-delta","id":"text-1","delta":"chat streaming is connected. Retrieval is not enabled yet."}

data: {"type":"text-end","id":"text-1"}

data: {"type":"finish","finishReason":"stop"}

data: [DONE]

```

The assistant `messageId` must be the ID saved to the database. The response is explicitly a stub, not a grounded research answer.

### Persistence and cancellation invariants

1. Verify the caller and ownership before accessing history or accepting a turn.
2. Atomically accept the new message and allocate its sequence. Use its UUID as a retry/idempotency key.
3. Allow at most one active turn per thread using database-backed coordination; process-local locks and unprotected `max(sequence) + 1` are insufficient.
4. Stream the stub in short asynchronous chunks without blocking the event loop.
5. Commit the complete assistant message and update thread activity before emitting successful `finish`. History must be reloadable when the client sees completion.
6. On cancellation, timeout, or failure before completion, retain the accepted user message but do not save an incomplete assistant message as a completed answer. Reconcile the UI with stored history.
7. A cancellation racing with an already committed completion can still leave a complete answer in history. History remains authoritative.
8. A repeated completed message ID with identical content replays the stored answer without inserting duplicates. A conflicting payload or active turn returns `409`. Interrupted turns must release or expire their database reservation so the thread cannot remain permanently blocked.
9. Apply a bounded turn timeout (30 seconds for this stub); no resumable-stream endpoint is introduced.

Use Supabase user-scoped reads with RLS where practical. Privileged user provisioning and coordinated message writes must remain backend-only. If implemented as service-role RPC transactions, revoke public/anon/authenticated execution, accept only server-verified identity, and re-check ownership inside each transaction. Do not grant browser clients the ability to forge assistant messages merely to make inserts work. Final SQL/RPC and schema changes belong to Step 2 and need explicit review.

### Errors

Before streaming: normal FastAPI JSON errors (`detail`), with `401` and `WWW-Authenticate: Bearer` for invalid authentication, `404` for inaccessible threads, `409` for turn conflicts, `413` for oversized bodies, `422` for invalid payloads, and sanitized `502`/`503` for upstream failures. Do not classify an unavailable Supabase service as an invalid login.

After streaming begins, HTTP status cannot change. Emit `{"type":"error","errorText":"Unable to complete this response. Please try again."}` and terminate without a successful finish. Do not leak credentials, SQL details, or upstream exception bodies. Client cancellation may close the connection before an error/abort frame can be delivered.

## Verification gates

Backend automated tests must mock auth/persistence boundaries and cover payload validation, missing/invalid tokens, ownership isolation, ordered history, stream frames, persistence failure, retries, concurrent-turn conflicts, cancellation, and timeouts. Current auth endpoint tests override `get_current_user` for valid/invalid outcomes; they do not independently prove Supabase token verification.

Database constraints, RLS, and transaction coordination require separate integration verification against a disposable/local database. Unit mocks and Alembic discovery alone are not sufficient evidence.

Frontend checks: `npm ci`, `npm run lint`, and `npm run build`, with CI placeholders and no live service calls.

Manual acceptance, after approved schema setup: sign in, create a thread, send a message, watch the stub stream, reload, reopen the thread, and confirm ordered persisted history. Also test sign-out, cancellation, unavailable backend, and a second user's inability to access the first user's thread.

Approval of a code/schema-preparation step does not authorize live database access, migration execution, commits, or pushes. Frontend SDK installation belongs to the separately approved frontend implementation step.
