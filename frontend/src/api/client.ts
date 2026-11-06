import type {
  Collection,
  CollectionCreate,
  CollectionReindex,
  Document,
  ChunkDetail,
  Diagnostics,
  SupportTicket,
  Health,
  Job,
  JobQueued,
  Model,
  Profile,
  Session,
  SessionSummary,
  UploadResponse,
} from "./types";

export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Turns FastAPI error bodies ({detail: string | [{msg}]}) into one line. */
export async function errorFromResponse(response: Response): Promise<ApiError> {
  let message = `${response.status} ${response.statusText}`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) {
      message = body.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
    }
  } catch {
    // not JSON; keep the status line
  }
  return new ApiError(response.status, message);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) throw await errorFromResponse(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function json(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export interface DocumentFilters {
  collection_id?: number;
  trashed?: boolean;
  q?: string;
  tag?: string;
}

export const api = {
  // health reports 503 when down but still sends the full body
  health: async (): Promise<Health> => {
    const response = await fetch(`${API_BASE}/health`);
    if (response.ok || response.status === 503) return (await response.json()) as Health;
    throw await errorFromResponse(response);
  },

  diagnostics: () => request<Diagnostics>("/diagnostics"),
  createSupportTicket: (note: string) => request<SupportTicket>("/support/tickets", json("POST", { note })),

  documents: (filters: DocumentFilters = {}) =>
    request<Document[]>(`/documents${query({ ...filters, limit: 500 })}`),
  upload: (files: File[], options: { collectionId?: number; tags?: string } = {}) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    if (options.collectionId !== undefined) form.append("collection_id", String(options.collectionId));
    if (options.tags) form.append("tags", options.tags);
    return request<UploadResponse>("/documents", { method: "POST", body: form });
  },
  deleteDocument: (id: number) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  restoreDocument: (id: number) => request<Document>(`/documents/${id}/restore`, json("POST")),
  chunk: (id: number) => request<ChunkDetail>(`/chunks/${id}`),
  reindexDocument: (id: number) => request<JobQueued>(`/documents/${id}/reindex`, json("POST")),

  collections: (includeInactive = false) =>
    request<Collection[]>(`/collections${query({ include_inactive: includeInactive })}`),
  createCollection: (body: CollectionCreate) => request<Collection>("/collections", json("POST", body)),
  reindexCollection: (id: number, body: CollectionReindex = {}) =>
    request<JobQueued>(`/collections/${id}/reindex`, json("POST", body)),

  jobs: () => request<Job[]>(`/jobs${query({ limit: 200 })}`),
  retryJob: (id: number) => request<Job>(`/jobs/${id}/retry`, json("POST")),
  cancelJob: (id: number) => request<Job>(`/jobs/${id}/cancel`, json("POST")),

  sessions: () => request<SessionSummary[]>(`/sessions${query({ limit: 100 })}`),
  session: (id: number) => request<Session>(`/sessions/${id}`),
  feedback: (messageId: number, thumbsUp: boolean) =>
    request<unknown>(`/messages/${messageId}/feedback`, json("POST", { thumbs_up: thumbsUp })),

  models: () => request<Model[]>("/models"),
  profiles: () => request<Profile[]>("/profiles"),
};
