import { DefaultChatTransport } from "ai";
import type { UIMessage } from "ai";

import { env } from "./env";
import { authenticatedFetch, HttpError } from "./http";

export const MAX_MESSAGE_LENGTH = 16_000;

// These types match the backend's camelCase JSON responses.
export type ChatThread = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  parts: { type: "text"; text: string }[];
  metadata: {
    sequence: number;
    createdAt: string;
  };
};

export type ThreadPage = {
  threads: ChatThread[];
  nextCursor: string | null;
};

export type MessagePage = {
  thread: ChatThread;
  messages: ChatMessage[];
  nextAfterSequence: number | null;
};

// Stored messages include metadata; newly streamed messages may not have it yet.
export type ChatUIMessage = UIMessage<ChatMessage["metadata"]>;

export const chatTransport = new DefaultChatTransport<ChatUIMessage>({
  api: `${env.apiBaseUrl}/chat/stream`,
  headers: { Accept: "text/event-stream" },
  fetch: authenticatedFetch,
  prepareSendMessagesRequest: ({ id, messages, trigger }) => {
    const message = messages.at(-1);
    const part = message?.parts[0];
    if (
      trigger !== "submit-message" ||
      message?.role !== "user" ||
      message.parts.length !== 1 ||
      part?.type !== "text" ||
      !part.text.trim() ||
      part.text.length > MAX_MESSAGE_LENGTH
    ) {
      throw new Error("Only a new text message can be sent.");
    }

    // Do not send SDK metadata, assistant messages, or browser-owned history.
    return {
      body: {
        threadId: id,
        trigger,
        messages: [{
          id: message.id,
          role: "user",
          parts: [{ type: "text", text: part.text }],
        }],
      },
    };
  },
});

export function streamErrorMessage(error: Error): string {
  if (error instanceof HttpError) {
    if (error.status === 401) return "Your session expired. Please sign in again.";
    if (error.status === 404) return "This conversation is no longer available to you.";
    if (error.status === 409) return "This conversation is busy or the message conflicts with a previous turn.";
    if (error.status === 413 || error.status === 422) return "The message was rejected. Send one nonblank text message within the size limit.";
    if (error.status === 502 || error.status === 503) return "Chat storage is unavailable. Please try again shortly.";
  }
  // Do not display arbitrary proxy responses or internal stream-parser errors.
  return "The response could not be completed. Please check your connection.";
}
