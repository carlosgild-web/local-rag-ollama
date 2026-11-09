import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { postEventStream } from "@/api/sse";
import type { Message, Source } from "@/api/types";
import { keys } from "./queries";

export interface PendingAnswer {
  question: string;
  answer: string;
  sources: Source[];
  status: "streaming" | "stopped" | "error";
  error?: string;
}

/**
 * Sends one question to POST /api/chat and accumulates the streamed answer.
 * When the stream ends the session is refetched and the saved messages
 * replace the pending answer. After Stop, the partial answer stays on
 * screen until the server has saved it (it saves on disconnect).
 */
export function useChatStream(onSession: (id: number) => void) {
  const client = useQueryClient();
  const [pending, setPending] = useState<PendingAnswer | null>(null);
  const controller = useRef<AbortController | null>(null);
  const sessionRef = useRef<number | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const ask = useCallback(
    async (
      question: string,
      sessionId: number | null,
      collectionId?: number,
      extra?: Record<string, unknown>,
    ) => {
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      setPending({ question, answer: "", sources: [], status: "streaming" });

      let session = sessionId;
      sessionRef.current = sessionId;
      try {
        const body = { question, session_id: sessionId, collection_id: collectionId ?? null, ...extra };
        for await (const message of postEventStream("/chat", body, abort.signal)) {
          switch (message.event) {
            case "session":
              session = message.data.session_id;
              sessionRef.current = session;
              if (sessionId === null) onSession(session);
              break;
            case "sources":
              setPending((p) => p && { ...p, sources: message.data });
              break;
            case "token":
              setPending((p) => p && { ...p, answer: p.answer + message.data.text });
              break;
            case "error":
              throw new Error(message.data.detail);
            case "done":
              break;
          }
        }
        if (session !== null) {
          // Load the saved messages before dropping the pending answer, so
          // the view never flashes empty.
          const id = session;
          await client.fetchQuery({ queryKey: keys.session(id), queryFn: () => api.session(id) });
        }
        await client.invalidateQueries({ queryKey: keys.sessions });
        setPending(null);
      } catch (error) {
        if (abort.signal.aborted) return;
        setPending((p) => p && { ...p, status: "error", error: (error as Error).message });
      } finally {
        if (controller.current === abort) controller.current = null;
      }
    },
    [client, onSession],
  );

  /** Stops generating but keeps the partial answer visible, then swaps in
   * the saved message once the server has written it. */
  const stop = useCallback(async () => {
    controller.current?.abort();
    controller.current = null;
    const id = sessionRef.current;
    setPending((p) => p && { ...p, status: "stopped" });
    if (id !== null) {
      for (let attempt = 0; attempt < 15; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const saved = await client
          .fetchQuery({ queryKey: keys.session(id), queryFn: () => api.session(id) })
          .catch(() => null);
        if (saved?.messages.at(-1)?.role === "assistant") break;
      }
    }
    setPending((p) => (p?.status === "stopped" ? null : p));
    client.invalidateQueries({ queryKey: keys.sessions });
  }, [client]);

  /** Drops any pending answer at once (starting a new chat). */
  const reset = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setPending(null);
  }, []);

  return { pending, ask, stop, reset, isStreaming: pending?.status === "streaming" };
}

/**
 * True when the saved conversation already ends with this question. The server
 * stores the question as soon as the answer starts, so once the session is
 * loaded the pending question must not be shown a second time.
 */
export function endsWithQuestion(messages: Message[], question: string) {
  const last = messages.at(-1);
  return last?.role === "user" && last.content === question;
}
