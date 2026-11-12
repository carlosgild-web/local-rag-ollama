// Mirrors backend/app/api/schemas.py. Times are ISO strings in UTC.

export interface ComponentHealth {
  ok: boolean;
  detail: string | null;
}

export interface Health {
  status: "ok" | "degraded" | "down";
  simulated: string[];
  ollama: ComponentHealth;
  sqlite: ComponentHealth;
  vector_store: ComponentHealth;
  job_worker: ComponentHealth;
}

export type CheckStatus = "ok" | "warn" | "fail" | "skip";

export interface DiagnosticAction {
  kind: "pull_model" | "reindex_collection" | "open_queue" | "open_collections";
  label: string;
  target: string | null;
}

/** One troubleshooter check (GET /api/diagnostics). */
export interface DiagnosticCheck {
  id: string;
  component: "ollama" | "sqlite" | "vector_store" | "jobs";
  title: string;
  status: CheckStatus;
  detail: string;
  cause: string | null;
  fix: string | null;
  commands: string[];
  action: DiagnosticAction | null;
}

export interface Diagnostics {
  status: "ok" | "warn" | "fail";
  checks: DiagnosticCheck[];
  simulated: string[];
  ran_at: string;
}

/** A prefilled service-desk incident (GET /api/support/draft). */
export interface SupportDraft {
  environment: {
    computer_name: string;
    user_name: string;
    os: string;
    app_version: string;
    python: string;
    configuration_item: string;
    ollama_base_url: string;
    chat_model: string;
    embedding_model: string;
    data_dir: string;
  };
  category: string;
  subcategory: string;
  assignment_group: string;
  impact: number;
  urgency: number;
  priority: string;
  short_description: string;
  system_status: "ok" | "warn" | "fail";
  problems: { title: string; status: string; detail: string; cause: string | null; fix: string | null }[];
  simulated_faults: string[];
}

export interface SupportTicketIn {
  caller_name: string;
  contact?: string;
  best_time_to_contact?: string;
  impact: number;
  urgency: number;
  short_description: string;
  description: string;
  started_at?: string;
  recent_changes?: string;
  users_affected?: string;
  steps_to_reproduce?: string;
}

/** A filed incident: simulated, saved locally, never sent. */
export interface SupportTicket {
  number: string;
  saved_to: string;
  incident: Record<string, unknown> & {
    state: string;
    opened_at: string;
    response_due: string;
    priority: string;
    assignment_group: string;
  };
}

export interface UploadRules {
  extensions: string[];
  max_upload_mb: number;
}

export type UploadCheckStatus =
  | "new"
  | "new_version"
  | "duplicate"
  | "name_in_trash"
  | "unsupported"
  | "empty"
  | "too_large";

export type IntakeStatus = UploadCheckStatus | "unreadable" | "pending";

/** One dropped file with the app's suggestions (GET /api/intake/{id}). */
export interface IntakeFile {
  key: string;
  name: string;
  path: string;
  size: number;
  status: IntakeStatus;
  message: string;
  /** false: can't or needn't be processed (duplicate, unreadable…). */
  include: boolean;
  /** "existing:<collection id>" or "new:<group>". */
  shelf: string | null;
  confidence: "high" | "low";
  reason: string;
  tags: string[];
  alternatives: string[];
}

export interface IntakeShelf {
  ref: string;
  name: string;
  description: string;
  existing: boolean;
  named_by: "model" | "keywords" | "existing" | "";
}

export interface Intake {
  batch_id: string;
  /** "staged" while the analysis runs, then "ready". */
  state: "staged" | "ready";
  files: IntakeFile[];
  shelves: IntakeShelf[];
}

export interface IntakeStarted {
  batch_id: string;
  job_id: number;
  files: number;
}

export interface IntakeConfirm {
  new_shelves: Record<string, string>;
  files: { key: string; include: boolean; shelf: string; tags: string[] }[];
}

export interface IntakeConfirmed {
  job_ids: number[];
  created_shelves: { ref: string; id: number; name: string }[];
}

/** What would happen to one file if uploaded now (POST /api/documents/check). */
export interface UploadCheckResult {
  name: string;
  status: UploadCheckStatus;
  message: string;
  document_id: number | null;
  existing_filename: string | null;
  existing_shelf: string | null;
  existing_version: number | null;
  next_version: number | null;
  existing_since: string | null;
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
  /** Searched by Luna, the employee portal assistant. */
  portal_visible: boolean;
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

/** GET /demo/files: one original demo document. */
export interface DemoFile {
  /** The shelf it loads into. */
  shelf: string;
  name: string;
  /** File extension, e.g. "pdf". */
  type: string;
  size: number;
  /** PDF and text open in a tab; Word files download. */
  opens_in_browser: boolean;
}

/** GET /demo: whether the console should offer to load the demo company. */
export interface DemoStatus {
  available: boolean;
  /** Documents in the library, not counting the trash. */
  documents: number;
  job: Job | null;
}

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
  /** What the job is about: a file name or "shelf <name>". */
  subject: string | null;
  /** Plain-language outcome, e.g. why an upload was skipped. */
  note: string | null;
  created_at: string;
  updated_at: string;
}

/** The passage behind a citation. */
export interface ChunkDetail {
  id: number;
  text: string;
  document_id: number;
  filename: string;
  collection_id: number;
  version_id: number;
  version_number: number;
  page: number | null;
  heading: string | null;
  retired: boolean;
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
  citation_status: CitationStatus | null;
}

/** ok: every [n] points at a source; missing: no citation; invalid: a
 * number with no source; not_applicable: "not found" answers. */
export type CitationStatus = "ok" | "missing" | "invalid" | "not_applicable";

/** Where a chat came from: the RAG console or the employee portal. */
export type Channel = "admin" | "intranet";

export interface SessionSummary {
  id: number;
  title: string;
  created_at: string;
  message_count: number;
  collection_id: number | null;
  channel: Channel;
}

export interface Session {
  id: number;
  title: string;
  created_at: string;
  collection_id: number | null;
  channel: Channel;
  messages: Message[];
}

export interface Model {
  name: string;
  size: number | null;
  modified_at: string | null;
  family: string | null;
  parameter_size: string | null;
  capabilities: string[];
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
  | {
      event: "done";
      data: { message_id: number; rag_profile_id: number; not_found: boolean; citation_status: CitationStatus };
    }
  | { event: "error"; data: { detail: string } };
