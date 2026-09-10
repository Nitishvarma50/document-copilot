import { useState } from "react";
import { NavLink } from "react-router-dom";

import type { ChatThread } from "../../lib/chat";

type ChatSidebarProps = {
  threads: ChatThread[];
  email: string | undefined;
  isLoading: boolean;
  isCreating: boolean;
  isSigningOut: boolean;
  error: string | null;
  hasMore: boolean;
  onCreate: () => void;
  onLoadMore: () => void;
  onRetry: () => void;
  onSignOut: () => void;
};

export function ChatSidebar({
  threads,
  email,
  isLoading,
  isCreating,
  isSigningOut,
  error,
  hasMore,
  onCreate,
  onLoadMore,
  onRetry,
  onSignOut,
}: ChatSidebarProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <aside className="chat-sidebar" aria-label="Conversation sidebar">
      <div className="chat-sidebar-heading">
        <p className="eyebrow">Document Copilot</p>
        <button
          type="button"
          className="chat-button chat-mobile-toggle"
          aria-expanded={isExpanded}
          aria-controls="chat-sidebar-content"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? "Hide chats" : "Show chats"}
        </button>
      </div>

      <div
        id="chat-sidebar-content"
        className={`chat-sidebar-content${isExpanded ? " is-expanded" : ""}`}
      >
        <button
          type="button"
          className="chat-button chat-button-primary"
          disabled={isCreating || isLoading || isSigningOut}
          onClick={() => {
            setIsExpanded(false);
            onCreate();
          }}
        >
          {isCreating ? "Creating…" : "+ New chat"}
        </button>

        <nav className="chat-thread-nav" aria-label="Conversations">
          <h2>Conversations</h2>
          <ul className="chat-thread-list">
            {threads.map((thread) => (
              <li key={thread.id}>
                <NavLink
                  to={`/chat/${thread.id}`}
                  className={({ isActive }) =>
                    `chat-thread-link${isActive ? " is-active" : ""}`
                  }
                  title={thread.title}
                  onClick={() => setIsExpanded(false)}
                >
                  {thread.title}
                </NavLink>
              </li>
            ))}
          </ul>

          {isLoading && <p role="status">Loading conversations…</p>}
          {!isLoading && !error && threads.length === 0 && (
            <p className="chat-muted">No conversations yet.</p>
          )}
          {error && (
            <div className="chat-inline-error">
              <p className="form-error" role="alert">{error}</p>
              <button
                type="button"
                className="chat-button"
                disabled={isLoading || isCreating || isSigningOut}
                onClick={onRetry}
              >
                Try again
              </button>
            </div>
          )}
          {hasMore && !error && (
            <button
              type="button"
              className="chat-button chat-load-more"
              disabled={isLoading || isCreating || isSigningOut}
              onClick={onLoadMore}
            >
              Load more
            </button>
          )}
        </nav>

        <div className="chat-account">
          <p title={email}>{email ?? "Signed in"}</p>
          <button
            type="button"
            className="chat-button"
            disabled={isSigningOut}
            onClick={onSignOut}
          >
            {isSigningOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
      </div>
    </aside>
  );
}
