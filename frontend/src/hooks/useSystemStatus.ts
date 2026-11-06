import type { Health } from "@/api/types";
import { useHealth } from "./queries";

export type SystemState = "checking" | "ok" | "degraded" | "down" | "unreachable";

/** What the app can do right now, and why not. */
export interface SystemStatus {
  state: SystemState;
  health: Health | undefined;
  simulated: string[];
  /** Read documents, chats and settings: needs the database and search index. */
  canBrowse: boolean;
  /** Ask questions: also needs Ollama. */
  canChat: boolean;
  /** Upload, reindex, rebuild: also needs the job worker. */
  canProcess: boolean;
  /** Plain-language reasons, e.g. "Ollama isn't running". */
  browseBlocked: string | null;
  chatBlocked: string | null;
  processBlocked: string | null;
  /** One sentence for the status bar. */
  headline: string;
}

const REASON = {
  unreachable: "the app server isn't answering",
  sqlite: "the database can't be opened",
  vector_store: "the search index doesn't answer",
  ollama: "Ollama isn't running",
  job_worker: "the background job worker has stopped",
} as const;

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function join(reasons: string[]): string | null {
  return reasons.length ? reasons.join(" and ") : null;
}

/** Turns the health poll (every 10 s) into one state plus what is paused.
 * "unreachable" means the backend itself didn't answer the last poll. */
export function useSystemStatus(): SystemStatus {
  const health = useHealth();
  const data = health.data;
  const unreachable = health.isError;
  const checking = !data && !unreachable;

  const browseReasons: string[] = unreachable
    ? [REASON.unreachable]
    : [
        ...(data && !data.sqlite.ok ? [REASON.sqlite] : []),
        ...(data && !data.vector_store.ok ? [REASON.vector_store] : []),
      ];
  const chatReasons = [...browseReasons, ...(!unreachable && data && !data.ollama.ok ? [REASON.ollama] : [])];
  const processReasons = [
    ...chatReasons,
    ...(!unreachable && data && !data.job_worker.ok ? [REASON.job_worker] : []),
  ];

  const state: SystemState = checking ? "checking" : unreachable ? "unreachable" : (data?.status ?? "checking");

  let headline = "";
  if (state === "unreachable") {
    headline = "Can't reach the app server. Nothing works until it's running again.";
  } else if (state === "down") {
    headline = `System down: ${join(browseReasons)}. Most features are paused.`;
  } else if (state === "degraded") {
    const paused = chatReasons.length > browseReasons.length ? "chat and document processing are" : "uploads and reindexing are";
    headline = `${capitalize(join(processReasons) ?? "Something isn't working")}: ${paused} paused.`;
  }

  return {
    state,
    health: data,
    simulated: data?.simulated ?? [],
    canBrowse: !checking && browseReasons.length === 0,
    canChat: !checking && chatReasons.length === 0,
    canProcess: !checking && processReasons.length === 0,
    browseBlocked: join(browseReasons),
    chatBlocked: join(chatReasons),
    processBlocked: join(processReasons),
    headline,
  };
}
