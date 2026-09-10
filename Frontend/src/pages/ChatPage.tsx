import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { ChatConversation } from "../components/chat/ChatConversation";
import { ChatSidebar } from "../components/chat/ChatSidebar";
import { api, loadThreadHistory } from "../lib/api";
import type { ChatThread, MessagePage, ThreadPage } from "../lib/chat";
import { HttpError } from "../lib/http";

type HandleRequestError = (error: unknown, fallback: string) => Promise<string>;

function mergeThreads(existing: ChatThread[], incoming: ChatThread[]): ChatThread[] {
  const byId = new Map(existing.map((thread) => [thread.id, thread]));
  for (const thread of incoming) byId.set(thread.id, thread);
  return [...byId.values()].sort(
    (a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt) || b.id.localeCompare(a.id),
  );
}

export function ChatPage() {
  const { user } = useAuth();
  // Never retain a previous account's conversations after an auth change.
  return <ChatWorkspace key={user?.id ?? "signed-out"} />;
}

function ChatWorkspace() {
  const { user, signOut } = useAuth();
  const { threadId } = useParams<{ threadId: string }>();
  const navigate = useNavigate();
  const [threadPage, setThreadPage] = useState<ThreadPage>({ threads: [], nextCursor: null });
  const [cursor, setCursor] = useState<string | null>(null);
  const [listAttempt, setListAttempt] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const createRequest = useRef<AbortController | null>(null);

  const handleRequestError = useCallback<HandleRequestError>(async (error, fallback) => {
    if (error instanceof HttpError) {
      if (error.status === 401) {
        try {
          await signOut();
        } catch {
          return "Your session expired. Please sign out and sign in again.";
        }
        return "Your session expired. Please sign in again.";
      }
      if (error.status === 404) return "This conversation was not found or is not available to you.";
      if (error.status === 422) return "This conversation link or request is invalid.";
      if (error.status === 502 || error.status === 503) {
        return "Chat storage is unavailable. Please try again shortly.";
      }
    }
    return fallback;
  }, [signOut]);

  useEffect(() => {
    const controller = new AbortController();

    void api.listThreads(cursor, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setThreadPage((previous) => ({
          threads: mergeThreads(previous.threads, page.threads),
          nextCursor: page.nextCursor,
        }));
        setListError(null);
      })
      .catch(async (error: unknown) => {
        if (controller.signal.aborted) return;
        const message = await handleRequestError(error, "Could not load conversations. Check your connection and try again.");
        if (!controller.signal.aborted) setListError(message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [cursor, listAttempt, handleRequestError]);

  useEffect(() => () => createRequest.current?.abort(), []);

  async function createThread() {
    // The ref guards even rapid clicks before React renders the disabled button.
    if (createRequest.current || isLoading || isSigningOut) return;
    const controller = new AbortController();
    createRequest.current = controller;
    setIsCreating(true);
    setActionError(null);

    try {
      const thread = await api.createThread(controller.signal);
      if (controller.signal.aborted) return;
      setThreadPage((previous) => ({
        ...previous,
        threads: mergeThreads(previous.threads, [thread]),
      }));
      navigate(`/chat/${thread.id}`);
    } catch (error) {
      if (controller.signal.aborted) return;
      const message = await handleRequestError(error, "Could not confirm conversation creation. Refresh the conversation list before trying again.");
      if (!controller.signal.aborted) setActionError(message);
    } finally {
      if (!controller.signal.aborted) {
        createRequest.current = null;
        setIsCreating(false);
      }
    }
  }

  const handleThreadUpdated = useCallback((thread: ChatThread) => {
    // Update the known thread immediately, then reload the first page for server ordering.
    setThreadPage((previous) => ({
      ...previous,
      threads: mergeThreads(previous.threads, [thread]),
    }));
    setIsLoading(true);
    setListError(null);
    setCursor(null);
    setListAttempt((attempt) => attempt + 1);
  }, []);

  function refreshThreads() {
    if (isCreating || isLoading || isSigningOut) return;
    setIsLoading(true);
    setListError(null);
    setActionError(null);
    setCursor(null);
    setListAttempt((attempt) => attempt + 1);
  }

  function retryList() {
    if (isCreating || isLoading || isSigningOut) return;
    setIsLoading(true);
    setListError(null);
    setListAttempt((attempt) => attempt + 1);
  }

  function loadMoreThreads() {
    if (!threadPage.nextCursor || isLoading || isCreating || isSigningOut) return;
    setIsLoading(true);
    setCursor(threadPage.nextCursor);
  }

  async function handleSignOut() {
    if (isSigningOut) return;
    setIsSigningOut(true);
    setActionError(null);
    try {
      await signOut();
    } catch {
      setActionError("Could not sign out. Please try again.");
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <main className="chat-shell">
      <ChatSidebar
        threads={threadPage.threads}
        email={user?.email}
        isLoading={isLoading}
        isCreating={isCreating}
        isSigningOut={isSigningOut}
        error={listError}
        hasMore={threadPage.nextCursor !== null}
        onCreate={() => void createThread()}
        onLoadMore={loadMoreThreads}
        onRetry={retryList}
        onSignOut={() => void handleSignOut()}
      />
      <div className="chat-main">
        {actionError && (
          <div className="chat-action-error">
            <p className="form-error" role="alert">{actionError}</p>
            <button
              type="button"
              className="chat-button"
              disabled={isLoading || isCreating || isSigningOut}
              onClick={refreshThreads}
            >
              Refresh conversations
            </button>
          </div>
        )}
        {threadId ? (
          <ThreadHistory
            key={threadId}
            threadId={threadId}
            onError={handleRequestError}
            onThreadUpdated={handleThreadUpdated}
          />
        ) : (
          <section className="chat-empty" aria-labelledby="chat-welcome-title">
            <p className="eyebrow">Your research workspace</p>
            <h1 id="chat-welcome-title">Start a conversation</h1>
            <p>Create a new chat or select a conversation to view its saved messages.</p>
            <button
              type="button"
              className="chat-button chat-button-primary"
              disabled={isCreating || isLoading || isSigningOut}
              onClick={() => void createThread()}
            >
              {isCreating ? "Creating…" : "+ New chat"}
            </button>
            <p className="chat-muted">Demo mode · Retrieval and AI-generated answers are not enabled yet.</p>
          </section>
        )}
      </div>
    </main>
  );
}

function ThreadHistory({ threadId, onError, onThreadUpdated }: {
  threadId: string;
  onError: HandleRequestError;
  onThreadUpdated: (thread: ChatThread) => void;
}) {
  const [history, setHistory] = useState<MessagePage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    async function loadHistory() {
      try {
        const page = await loadThreadHistory(threadId, controller.signal);
        if (controller.signal.aborted) return;
        setHistory(page);
        setError(null);
        onThreadUpdated(page.thread);
      } catch (requestError) {
        if (controller.signal.aborted) return;
        const message = await onError(requestError, "Could not load this conversation. Check your connection and try again.");
        if (!controller.signal.aborted) setError(message);
      }
    }

    void loadHistory();
    return () => controller.abort();
  }, [threadId, attempt, onError, onThreadUpdated]);

  if (error) {
    return (
      <section className="chat-empty" aria-label="Conversation unavailable">
        <h1>Unable to open conversation</h1>
        <p className="form-error" role="alert">{error}</p>
        <button
          type="button"
          className="chat-button"
          onClick={() => {
            setError(null);
            setAttempt((value) => value + 1);
          }}
        >
          Try again
        </button>
      </section>
    );
  }

  if (!history) {
    return <div className="chat-empty"><p role="status">Loading conversation…</p></div>;
  }

  return (
    <ChatConversation
      thread={history.thread}
      messages={history.messages}
      onThreadUpdated={onThreadUpdated}
      onHistoryError={onError}
    />
  );
}
