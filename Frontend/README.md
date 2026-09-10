# Document Copilot frontend

A Vite + React + TypeScript chat UI. Supabase handles sign-in; FastAPI owns chat history and response generation. The current response is an explicitly labelled fixed stub, not an LLM-generated research answer.

## Local setup

Use Node.js 22 or newer. From this directory:

```text
npm ci
npm run dev
```

Before starting, create `.env.local` using `.env.example` and supply:

- `VITE_API_BASE_URL`: FastAPI URL, such as `http://localhost:8000`.
- `VITE_SUPABASE_URL`: Supabase project URL.
- `VITE_SUPABASE_ANON_KEY`: public browser key, never the backend service-role key.

The backend must allow the frontend origin through CORS. Live chat also requires the database schema described in [the migration guide](../Docs/chat-backend-migrations.md). Building the frontend does not validate database readiness.

## Routes and files

- `/login` and `/signup`: Supabase authentication.
- `/` redirects to `/chat`.
- `/chat`: protected conversation list and new-chat empty state.
- `/chat/:threadId`: saved messages and streaming composer.

| File under `src/` | Responsibility |
| --- | --- |
| `pages/ChatPage.tsx` | Thread creation/listing, navigation, and paginated history loading |
| `components/chat/ChatSidebar.tsx` | Conversation links, New chat, and sign-out |
| `components/chat/ChatConversation.tsx` | `useChat`, Send/Stop, input validation, and post-stream history reconciliation |
| `lib/chat.ts` | Chat types and AI SDK transport configuration |
| `lib/http.ts` | Current-token authenticated fetch and the existing JSON helpers |
| `lib/api.ts` | Thread REST requests and the shared full-history loader |

## How streaming works

```text
Composer → useChat.sendMessage({ text })
         → custom transport sends only the new user message
         → authenticatedFetch attaches the current Supabase token
         → FastAPI POST /chat/stream
         → SDK reads SSE text events and updates React messages
         → sendMessage settles (success, cancellation, or error)
         → reload saved history, replace local messages, and refresh the sidebar
```

The installed pair is `ai@7.0.94` and `@ai-sdk/react@4.0.97`. The SDK manages frontend chat state and stream parsing; it does not generate answers or persist history. It does not require Vercel hosting.

Initial history is loaded before mounting `useChat`. User message IDs use `crypto.randomUUID()`, and the backend supplies the persisted assistant ID in the stream. The transport strips old history and SDK metadata to match the [API contract](../Docs/chat-api-contract.md).

`authenticatedFetch` returns successful responses without reading their bodies. Ordinary REST helpers then parse JSON; the SDK consumes streaming responses. Stop and thread unmount both abort the stream. Cancelling a request does not undo an already committed database write.

## Current boundaries

- Enter sends; Shift+Enter inserts a newline. Blank input and input over 16,000 JavaScript string units are blocked (a conservative limit for the backend's 16,000-character maximum).
- Pending sends disable the composer and expose Stop. The composer stays disabled while saved history is being refreshed.
- After success, cancellation, or failure, the UI waits for the stream to settle, reloads every history page, and replaces the local message list. Unsaved assistant text is removed; a complete answer committed during cancellation is retained.
- If refreshing history fails, **Retry history** repeats only the read, never the message submission. Sending stays disabled until history is available; no full-page reload is required.
- If the submitted message is absent from saved history, its text is restored to the input. Sending that text unchanged explicitly retries with the original UUID. Messages are never automatically resent.
- The header and sidebar title/activity are refreshed from server data, including when reopening a thread that completed offscreen. Sidebar refreshes deduplicate existing entries rather than dropping previously loaded conversations.
- Leaving a thread or signing out aborts its stream and history requests; delayed results cannot overwrite the new conversation.
- No retrieval, real model calls, Markdown renderer, attachments, tools, citations, or regeneration are included.

## Verification

```text
npm run lint
npm run build
```

Local transport smoke checks with mocked auth/fetch cover request shape, fresh tokens, fragmented SSE (including Unicode), typed HTTP errors, in-stream failures, cancellation, and full-history pagination.

Temporary headless Chrome checks exercised the actual React app with mocked Supabase/backend boundaries: completion and sidebar updates, duplicate sends/creates, cancellation/commit races, restored-draft UUID reuse, history-read failures and retry, stream errors, navigation with late responses, sign-out failures, and the mobile sidebar. Desktop/mobile screenshots were also reviewed. No extra test package was installed; a maintained frontend test suite remains deferred.

Live authentication, database persistence, ownership enforcement, and end-to-end acceptance remain unverified. The current build also reports a non-blocking bundle-size warning. Live verification requires separate approval and a prepared backend/database; see the migration guide rather than applying migrations automatically.
