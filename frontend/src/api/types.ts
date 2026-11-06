// Mirrors backend/app/api/schemas.py. Times are ISO strings in UTC.

export interface ComponentHealth {
  ok: boolean;
  detail: string | null;
}

export interface Health {
  status: "ok" | "degraded" | "down";
  ollama: ComponentHealth;
  sqlite: ComponentHealth;
  vector_store: ComponentHealth;
  job_worker: ComponentHealth;
}

export interface QueuedUpload {
  job_id: number;
  filename: string;
}

export interface UploadResponse {
  jobs: QueuedUpload[];
}

export interface Document {
  id: number;
  collection_id: number;
  filename: string;
  tags: string[];
  active_version_id: number | null;
  active_version_number: number | null;
  version_count: number;
  trashed_at: string | null;
  created_at: string;
}

export interface Collection {
  id: number;
  name: string;
  chroma_collection: string;
  embedding_model: string;
  chunk_size_tokens: number;
  chunk_overlap_pct: number;
  is_active: boolean;
  created_at: string;
  document_count: number;
}

export interface CollectionCreate {
  name: string;
  embedding_model?: string;
  chunk_size_tokens?: number;
  chunk_overlap_pct?: number;
}

export type CollectionReindex = Omit<CollectionCreate, "name">;

export interface JobQueued {
  job_id: number;
  mode: "in_place" | "blue_green" | null;
  target_collection_id: number | null;
}

export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface Job {
  id: number;
  job_type: string;
  status: JobStatus;
  progress: number;
  error: string | null;
  result: Record<string, unknown> | null;
  retries: number;
  cancel_requested: boolean;
  document_id: number | null;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Source {
  rank: number;
  chunk_id: number;
  score: number;
  document_id: number | null;
  filename: string | null;
  page: number | null;
  heading: string | null;
}

export interface Feedback {
  message_id: number;
  thumbs_up: boolean;
  comment: string | null;
  created_at: string;
}

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  rag_profile_id: number | null;
  created_at: string;
  sources: Source[];
  feedback: Feedback | null;
}

export interface SessionSummary {
  id: number;
  title: string;
  created_at: string;
  message_count: number;
  collection_id: number | null;
}

export interface Session {
  id: number;
  title: string;
  created_at: string;
  collection_id: number | null;
  messages: Message[];
}

export interface Model {
  name: string;
  size: number | null;
  modified_at: string | null;
  family: string | null;
  parameter_size: string | null;
}

export interface Profile {
  id: number;
  name: string;
  version: number;
  chat_model: string;
  embedding_model: string;
  chunk_size_tokens: number;
  chunk_overlap_pct: number;
  retrieval_top_k: number;
  temperature: number;
  system_prompt: string;
  is_active: boolean;
  created_at: string;
}

// Server-sent events of POST /api/chat, in order.
export type ChatEvent =
  | { event: "session"; data: { session_id: number; user_message_id: number } }
  | { event: "sources"; data: Source[] }
  | { event: "token"; data: { text: string } }
  | { event: "done"; data: { message_id: number; rag_profile_id: number; not_found: boolean } }
  | { event: "error"; data: { detail: string } };
