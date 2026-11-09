import { API_BASE, errorFromResponse } from "./client";
import type { ChatEvent } from "./types";

/**
 * Reads a server-sent event stream from a POST request. EventSource only
 * does GET, so this parses the `event:` / `data:` lines from fetch directly.
 * Aborting the signal closes the connection; the backend keeps the partial
 * answer.
 */
export async function* postEventStream<E extends { event: string; data: unknown } = ChatEvent>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<E> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) throw await errorFromResponse(response);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const parsed = parseEvent<E>(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (parsed) yield parsed;
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseEvent<E>(block: string): E | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (data.length === 0) return null;
  return { event, data: JSON.parse(data.join("\n")) } as E;
}
