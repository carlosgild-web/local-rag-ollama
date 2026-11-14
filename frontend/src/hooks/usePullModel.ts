import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { postEventStream } from "@/api/sse";
import type { PullEvent } from "@/api/types";

export interface PullState {
  name: string;
  status: string; // Ollama's own words: "pulling manifest", "downloading", "success"…
  total: number | null;
  completed: number | null;
  phase: "running" | "done" | "error" | "cancelled";
  error?: string;
}

/** Pulls one model through POST /api/models/pull, streaming Ollama's progress.
 * Cancelling closes the connection, which stops Ollama's download. */
export function usePullModel() {
  const client = useQueryClient();
  const [state, setState] = useState<PullState | null>(null);
  const abort = useRef<AbortController | null>(null);

  const pull = useCallback(
    async (name: string) => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setState({ name, status: "starting", total: null, completed: null, phase: "running" });
      try {
        for await (const e of postEventStream<PullEvent>("/models/pull", { name }, controller.signal)) {
          if (e.event === "progress") {
            const { status, total, completed } = e.data;
            setState((s) => ({
              ...(s as PullState),
              status,
              // Ollama reports each layer separately; keep the big download's numbers.
              total: total ?? s?.total ?? null,
              completed: total ? (completed ?? 0) : (s?.completed ?? null),
            }));
          } else if (e.event === "done") {
            setState((s) => ({ ...(s as PullState), status: "success", phase: "done" }));
          } else {
            setState((s) => ({ ...(s as PullState), phase: "error", error: e.data.detail }));
          }
        }
        setState((s) =>
          s && s.phase === "running" ? { ...s, phase: "error", error: "The pull stopped before it finished." } : s,
        );
      } catch (err) {
        if (controller.signal.aborted) setState((s) => s && { ...s, phase: "cancelled" });
        else setState((s) => s && { ...s, phase: "error", error: err instanceof Error ? err.message : String(err) });
      } finally {
        if (abort.current === controller) abort.current = null;
        client.invalidateQueries({ queryKey: ["models"] });
        client.invalidateQueries({ queryKey: ["audit"] });
      }
    },
    [client],
  );

  const cancel = useCallback(() => abort.current?.abort(), []);
  const clear = useCallback(() => setState(null), []);
  return { state, pull, cancel, clear };
}
