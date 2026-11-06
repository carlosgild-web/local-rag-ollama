import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { postEventStream } from "@/api/sse";
import type { Source } from "@/api/types";
import { keys } from "./queries";

export interface PendingAnswer {
  question: string;
  answer: string;
  sources: Source[];
  status: "streaming" | "error";
  error?: string;
}

/**
 * Sends one question to POST /api/chat and accumulates the streamed answer.
 * When the stream ends the session is refetched and the saved messages
 * replace the pending answer.
 */
export function useChatStream(onSession: (id: number) => void) {
  const client = useQueryClient();
  const [pending, setPending] = useState<PendingAnswer | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const ask = useCallback(
    async (question: string, sessionId: number | null, collectionId?: number) => {
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      setPending({ question, answer: "", sources: [], status: "streaming" });

      let session = sessionId;
      try {
        const body = { question, session_id: sessionId, collection_id: collectionId ?? null };
        for await (const message of postEventStream("/chat", body, abort.signal)) {
          switch (message.event) {
            case "session":
              session = message.data.session_id;
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

  const stop = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setPending(null);
    client.invalidateQueries({ queryKey: keys.sessions });
    client.invalidateQueries({ queryKey: ["session"] });
  }, [client]);

  return { pending, ask, stop, isStreaming: pending?.status === "streaming" };
}
