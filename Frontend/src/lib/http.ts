import { env } from "./env";
import { supabase } from "./supabase";

export class HttpError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.details = details;
  }
}

function isJsonResponse(response: Response): boolean {
  return response.headers.get("content-type")?.includes("application/json") ?? false;
}

async function parseResponse(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }

  if (isJsonResponse(response)) {
    return response.json();
  }

  return response.text();
}

// Shared by JSON requests and the AI SDK. Successful bodies remain unread.
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const request = new Request(input, init);
  request.signal.throwIfAborted();
  const { data, error } = await supabase.auth.getSession();
  request.signal.throwIfAborted();

  if (error) throw new HttpError(503, "Unable to read your session. Please try again.");
  if (!data.session?.access_token) throw new HttpError(401, "Please sign in again.");

  const headers = new Headers(request.headers);
  headers.set("Authorization", `Bearer ${data.session.access_token}`);
  const response = await fetch(new Request(request, { headers }));

  if (!response.ok) {
    const body = await parseResponse(response).catch(() => undefined);
    const message =
      typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : `Request failed with status ${response.status}`;
    throw new HttpError(response.status, message, body);
  }

  return response;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await authenticatedFetch(`${env.apiBaseUrl}${path}`, { ...init, headers });
  return await parseResponse(response) as T;
}

export const http = {
  get: <T>(path: string, init?: RequestInit) =>
    request<T>(path, { ...init, method: "GET" }),
  post: <T>(path: string, body: unknown, init?: RequestInit) =>
    request<T>(path, {
      ...init,
      body: JSON.stringify(body),
      method: "POST",
    }),
};
