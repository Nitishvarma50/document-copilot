import type { ChatMessage, ChatThread, MessagePage, ThreadPage } from "./chat";
import { http } from "./http";

export type AuthenticatedUser = {
  id: string;
  email: string | null;
};

export const api = {
  getAuthenticatedUser: () =>
    http.get<AuthenticatedUser>("/auth/me"),

  createThread: (signal?: AbortSignal) =>
    http.post<ChatThread>("/threads", { title: "New chat" }, { signal }),

  listThreads: (cursor: string | null = null, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: "50" });
    if (cursor) query.set("cursor", cursor);
    return http.get<ThreadPage>(`/threads?${query}`, { signal });
  },

  getThreadMessages: (
    threadId: string,
    afterSequence = 0,
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({
      limit: "100",
      afterSequence: String(afterSequence),
    });
    return http.get<MessagePage>(
      `/threads/${encodeURIComponent(threadId)}/messages?${query}`,
      { signal },
    );
  },
};

// Initial loading and post-stream reconciliation must both read the full history.
export async function loadThreadHistory(
  threadId: string,
  signal?: AbortSignal,
): Promise<MessagePage> {
  const messages: ChatMessage[] = [];
  let afterSequence = 0;
  while (true) {
    signal?.throwIfAborted();
    const page = await api.getThreadMessages(threadId, afterSequence, signal);
    signal?.throwIfAborted();
    messages.push(...page.messages);
    if (page.nextAfterSequence === null) return { ...page, messages };
    if (page.nextAfterSequence <= afterSequence) throw new Error("Invalid history cursor");
    afterSequence = page.nextAfterSequence;
  }
}
