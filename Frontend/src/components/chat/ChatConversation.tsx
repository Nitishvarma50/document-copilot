import { useChat } from "@ai-sdk/react";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { loadThreadHistory } from "../../lib/api";
import { chatTransport, MAX_MESSAGE_LENGTH, streamErrorMessage } from "../../lib/chat";
import type { ChatMessage, ChatThread, ChatUIMessage } from "../../lib/chat";
import { HttpError } from "../../lib/http";

type ChatConversationProps = {
  thread: ChatThread;
  messages: ChatMessage[];
  onThreadUpdated: (thread: ChatThread) => void;
  onHistoryError: (error: unknown, fallback: string) => Promise<string>;
};

export function ChatConversation({
  thread, messages: initialMessages, onThreadUpdated, onHistoryError,
}: ChatConversationProps) {
  const [currentThread, setCurrentThread] = useState(thread);
  const [input, setInput] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isReloading, setIsReloading] = useState(false);
  const messageList = useRef<HTMLDivElement>(null);
  const sendInFlight = useRef(false);
  const reloadInFlight = useRef(false);
  const lifetime = useRef<AbortController | null>(null);
  const lastSubmission = useRef<{ id: string; text: string } | null>(null);
  const { messages, sendMessage, setMessages, clearError, status, stop, error } = useChat<ChatUIMessage>({
    id: thread.id,
    messages: initialMessages,
    transport: chatTransport,
    generateId: () => crypto.randomUUID(),
    onError: (streamError) => {
      if (!lifetime.current?.signal.aborted) setNotice(streamErrorMessage(streamError));
    },
    onFinish: ({ isAbort, isError, finishReason }) => {
      if (lifetime.current?.signal.aborted) return;
      if (isAbort) {
        setNotice("Response stopped. Only messages confirmed by saved history will be kept.");
      } else if (!isError && finishReason !== "stop") {
        setNotice("The stream ended without confirmed completion. Saved history determines which messages are kept.");
      }
    },
  });
  const isBusy = status === "submitted" || status === "streaming";
  const composerBlocked = isBusy || isReloading || Boolean(historyError);

  useEffect(() => {
    const element = messageList.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages]);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => {
      // Cancel both streaming and history reads when leaving this thread/account.
      controller.abort();
      void stop();
    };
  }, [stop]);

  async function reconcileHistory() {
    const signal = lifetime.current?.signal;
    if (!signal || signal.aborted || reloadInFlight.current) return;
    reloadInFlight.current = true;
    setIsReloading(true);

    try {
      const history = await loadThreadHistory(thread.id, signal);
      if (signal.aborted) return;
      // Called only after sendMessage settles, never while the SDK is streaming.
      setMessages(history.messages);
      setCurrentThread(history.thread);
      clearError();
      setHistoryError(null);

      const submitted = lastSubmission.current;
      if (submitted && !history.messages.some((message) => message.id === submitted.id)) {
        setInput((draft) => draft || submitted.text);
        setNotice("Your message is not in saved history. It is back in the input; sending it unchanged retries the same message.");
        // Keep its UUID for an explicit retry, since a cancelled write can finish later.
      } else {
        lastSubmission.current = null;
      }
      onThreadUpdated(history.thread);
    } catch (requestError) {
      if (signal.aborted) return;
      const message = await onHistoryError(requestError, "Could not refresh saved history. Check your connection and try again.");
      if (!signal.aborted) setHistoryError(message);
    } finally {
      reloadInFlight.current = false;
      if (!signal.aborted) setIsReloading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const signal = lifetime.current?.signal;
    if (!signal || signal.aborted || sendInFlight.current || reloadInFlight.current || composerBlocked || !input.trim() || input.length > MAX_MESSAGE_LENGTH) return;

    sendInFlight.current = true;
    setNotice(null);
    try {
      const submission = lastSubmission.current?.text === input
        ? lastSubmission.current
        : { id: crypto.randomUUID(), text: input };
      lastSubmission.current = submission;
      setInput("");
      // Explicit IDs let a retry reuse the original backend idempotency key.
      await sendMessage({
        id: submission.id,
        role: "user",
        parts: [{ type: "text", text: submission.text }],
      });
    } catch {
      if (!signal.aborted) setNotice("The message could not be sent. Saved history determines whether it was accepted.");
    } finally {
      // SDK errors normally resolve sendMessage and set error/status instead of throwing.
      if (!signal.aborted) await reconcileHistory();
      sendInFlight.current = false;
    }
  }

  return (
    <section className="chat-conversation" aria-labelledby="conversation-title">
      <header className="chat-header">
        <h1 id="conversation-title">{currentThread.title}</h1>
        <p className="chat-muted">Demo mode · Stub responses only</p>
      </header>

      <div className="chat-messages" ref={messageList}>
        {messages.length === 0 ? (
          <div className="chat-empty">
            <h2>Your conversation is ready</h2>
            <p>Send a message to try the streamed demo response.</p>
          </div>
        ) : (
          <ol className="chat-message-list" aria-label="Conversation messages">
            {messages.map((message) => (
              <li key={message.id} className={`chat-message chat-message-${message.role}`}>
                <article aria-label={message.role === "user" ? "Your message" : "Assistant message"}>
                  <p className="chat-message-author">
                    {message.role === "user" ? "You" : "Assistant"}
                  </p>
                  {message.parts.map((part, index) => part.type === "text" ? (
                    <p className="chat-message-text" key={index}>{part.text}</p>
                  ) : null)}
                </article>
              </li>
            ))}
          </ol>
        )}
      </div>

      <form className="chat-composer" onSubmit={(event) => void handleSubmit(event)}>
        <p className="chat-stream-status chat-muted" role="status">
          {isReloading ? "Syncing saved history…" : status === "submitted" ? "Sending message…" : status === "streaming" ? "Assistant is responding…" : ""}
        </p>
        {notice && <p className="chat-stream-error" role="status">{notice}</p>}
        {historyError && (
          <div className="chat-stream-error" role="alert">
            <p className="form-error">{historyError}</p>
            <p>Messages above may be incomplete. Refresh history before sending again.</p>
            <button
              type="button"
              className="chat-button"
              disabled={isBusy || isReloading}
              onClick={() => {
                if (!sendInFlight.current) void reconcileHistory();
              }}
            >
              Retry history
            </button>
            {error instanceof HttpError && error.status === 401 && (
              <Link to="/login">Sign in again</Link>
            )}
          </div>
        )}
        <label htmlFor="chat-message">Message</label>
        <div className="chat-composer-row">
          <textarea
            id="chat-message"
            rows={2}
            placeholder="Type a message…"
            aria-describedby="composer-note composer-count"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            maxLength={MAX_MESSAGE_LENGTH}
            required
            disabled={composerBlocked}
          />
          {isBusy ? (
            <button type="button" className="chat-button" onClick={() => void stop()}>
              Stop
            </button>
          ) : (
            <button
              type="submit"
              className="chat-button chat-button-primary"
              disabled={composerBlocked || !input.trim() || input.length > MAX_MESSAGE_LENGTH}
            >
              Send
            </button>
          )}
        </div>
        <div className="chat-composer-hints chat-muted">
          <p id="composer-note">Enter to send · Shift+Enter for a new line · Stub responses only</p>
          <p id="composer-count">{input.length.toLocaleString()} / {MAX_MESSAGE_LENGTH.toLocaleString()}</p>
        </div>
      </form>
    </section>
  );
}
