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

export type IntakeStatus = UploadCheckStatus | "unreadable" | "pending" | "similar";

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
  /** Almost the same text as an existing document under another name. */
  similar_to?: {
    document_id: number;
    filename: string;
    shelf_id: number;
    shelf: string;
    /** 0–1, compared word by word. */
    similarity: number;
  } | null;
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
  files: { key: string; include: boolean; shelf: string; tags: string[]; version_of?: number | null }[];
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
  /** Last new version or restore. */
  updated_at: string;
}

/** GET /documents/{id}/versions */
export interface DocumentVersion {
  id: number;
  version_number: number;
  sha256: string;
  ext: string;
  note: string | null;
  /** "upload": a file was added; "edit": its text was changed in the app's editor. */
  origin: "upload" | "edit";
  /** Who edited it (a typed name: there are no accounts). */
  edited_by: string | null;
  /** The version answers use. */
  is_active: boolean;
  chunk_count: number;
  created_at: string;
}

export interface VersionText {
  version_id: number;
  version_number: number;
  text: string;
}

export interface VersionDiff {
  a: number;
  b: number;
  /** Unified diff lines: "+" added, "-" removed, " " unchanged, "@@" a gap. */
  diff: string[];
}

export interface FeedbackSummary {
  helpful: number;
  not_helpful: number;
  recent_not_helpful: {
    message_id: number;
    session_id: number;
    channel: Channel;
    question: string;
    answer: string;
    comment: string | null;
    sources: string[];
    created_at: string;
  }[];
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

/** One audit log row (invariant 7): uploads, deletes, purges, rollbacks, settings. */
export interface AuditEntry {
  id: number;
  action: string;
  entity_type: string;
  entity_id: number | null;
  detail: string;
  created_at: string;
}

export interface AuditFilters {
  action?: string;
  entity_type?: string;
  limit?: number;
}

export interface JobQueued {
  job_id: number;
  mode: "in_place" | "blue_green" | null;
  target_collection_id: number | null;
}

export type JobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

/** GET /backups: one backup zip (decision 0015). */
export interface Backup {
  name: string;
  size: number;
  manifest: {
    app_version: string;
    schema_revision: string | null;
    created_at: string;
    /** "manual", "auto" or "before-restore". */
    reason: string;
    embedding_models: string[];
    counts: { documents: number; versions: number; shelves: number; chats: number };
  } | null;
  /** Set when the file can't be read as a backup. */
  error: string | null;
}

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
  /** The demo was loaded before v0.9.0 added the glossary, so its words are missing. */
  glossary_missing: boolean;
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
  /** Ollama holds it in memory right now. */
  loaded: boolean;
  /** Profiles and shelves that need it; deleting it is refused while this isn't empty. */
  used_by: string[];
}

/** Server-sent events of POST /api/models/pull. */
export type PullEvent =
  | { event: "progress"; data: { status: string; total?: number; completed?: number; digest?: string } }
  | { event: "done"; data: { name: string; status: string } }
  | { event: "error"; data: { detail: string } };

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

export interface ProfileVersion extends Profile {
  /** Chat answers recorded with this version (invariant 5). */
  answer_count: number;
  eval_run_count: number;
}

/** The fields the Profiles page edits; the rest are set per shelf. */
export interface ProfileIn {
  name: string;
  chat_model?: string;
  retrieval_top_k?: number;
  temperature?: number;
  system_prompt?: string;
}

export interface ProfileCompare {
  a: Profile;
  b: Profile;
  changes: { field: string; a: unknown; b: unknown }[];
  prompt_diff: string[];
}

// Watched folders (decision 0025).
export interface WatchedFolder {
  id: number;
  path: string;
  collection_id: number;
  collection_name: string;
  recursive: boolean;
  enabled: boolean;
  /** "watching", "starting" (just added), "paused", "error" (see error) or "stopped" (the watcher isn't running). */
  state: "watching" | "starting" | "paused" | "error" | "stopped";
  error: string | null;
  files_queued: number;
  last_scan_at: string | null;
  last_file_at: string | null;
  created_at: string;
}

export interface WatchedFolders {
  mode: "events" | "polling";
  running: boolean;
  poll_seconds: number;
  folders: WatchedFolder[];
}

export interface WatchScan {
  queued: number;
  known: number;
  skipped: number;
}

// POST /api/retrieve/inspect: the retrieval inspector (decision 0024).
export type InspectScope = "shelf" | "all" | "portal";

export interface InspectIn {
  question: string;
  scope: InspectScope;
  collection_id?: number;
  profile?: string;
  mode: RetrievalMode;
  top_k?: number;
  candidates?: number;
  /** Hybrid only: 0.5 = plain RRF (the chat), 1 = vectors only, 0 = keywords only. */
  vector_weight: number;
  /** Vector matches under this cosine similarity are dropped; 0 = off. */
  min_cosine: number;
  rerank?: boolean;
  include_prompt?: boolean;
}

export interface InspectChunk {
  rank: number;
  chunk_id: number;
  document_id: number;
  version_id: number | null;
  filename: string;
  page: number | null;
  heading: string | null;
  score: number;
  text: string;
  sent: boolean;
  vector_rank: number | null;
  vector_score: number | null;
  keyword_rank: number | null;
  keyword_score: number | null;
  fused_score: number | null;
  rerank_score: number | null;
}

export interface InspectOut {
  question: string;
  expanded_question: string;
  collection_ids: number[];
  profile_id: number;
  profile_name: string;
  profile_version: number;
  parameters: {
    mode: RetrievalMode;
    top_k: number;
    candidates: number;
    vector_weight: number;
    min_cosine: number;
    rerank: boolean;
  };
  reranker_available: boolean;
  chunks: InspectChunk[];
  prompt: string | null;
  timings: { embed_ms: number; embedding_cached: boolean; search_ms: number; rerank_ms: number | null; total_ms: number };
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

// --- Evaluation (decision 0019) ---------------------------------------------

export type RetrievalMode = "hybrid" | "vector" | "keyword";

export interface EvalSet {
  id: number;
  name: string;
  description: string;
  case_count: number;
  run_count: number;
  created_at: string;
}

export interface EvalCaseIn {
  question: string;
  /** null searches every shelf */
  shelf: string | null;
  expected_sources: string[];
  /** groups of alternatives: the answer needs one alternative of each group */
  required_facts: string[][];
  expect_not_found: boolean;
  kind: string;
  variant_group: string | null;
  expected_answer_notes: string | null;
}

export interface EvalCase extends EvalCaseIn {
  id: number;
  eval_set_id: number;
}

export interface EvalSetDetail extends EvalSet {
  cases: EvalCase[];
}

/** Rates are 0..1; null means "not measured" (e.g. no answers generated). */
export interface EvalMetrics {
  cases: number;
  errors: number;
  answerable: number;
  traps: number;
  hit_rate_at_5: number | null;
  hit_rate_at_1: number | null;
  mrr: number | null;
  retrieval_ms: number | null;
  pass_rate: number | null;
  variant_groups: number;
  variant_rate: number | null;
  answered_rate?: number | null;
  facts_rate?: number | null;
  trap_rate?: number | null;
  citation_rate?: number | null;
  faithfulness?: number | null;
  judged?: number;
  answer_ms?: number | null;
}

export interface EvalRunConfig {
  mode: RetrievalMode;
  /** bge-reranker-v2-m3 rescored the candidates (decision 0023); missing on older runs */
  rerank?: boolean;
  top_k: number;
  answers: boolean;
  judge: boolean;
  judge_model: string | null;
  /** citation numbers checked against the passages (decision 0020); missing on older runs */
  repair_citations?: boolean;
  /** missing on older runs */
  use_glossary?: boolean;
  glossary?: { term: string; means: string }[];
}

export interface EvalShelfSnapshot {
  shelf: string;
  collection_id: number;
  embedding_model: string;
  chunk_size_tokens: number;
  documents: number;
  chunks: number;
  fingerprint: string;
}

export interface EvalRun {
  id: number;
  eval_set_id: number;
  eval_set_name: string;
  rag_profile_id: number | null;
  profile: string | null;
  chat_model: string | null;
  label: string;
  config: EvalRunConfig;
  index_snapshot: EvalShelfSnapshot[];
  metrics: EvalMetrics | null;
  status: JobStatus;
  progress: number;
  error: string | null;
  job_id: number | null;
  created_at: string;
  finished_at: string | null;
}

export interface EvalRetrieved {
  chunk_id: number;
  filename: string;
  score: number;
}

export interface EvalResult {
  id: number;
  eval_case_id: number | null;
  question: string;
  shelf: string | null;
  kind: string;
  variant_group: string | null;
  expect_not_found: boolean;
  expected_sources: string[];
  required_facts: string[][];
  retrieved: EvalRetrieved[];
  first_relevant_rank: number | null;
  answer: string | null;
  not_found: boolean | null;
  missing_facts: string[][] | null;
  citation_status: string | null;
  cited_sources: string[] | null;
  faithfulness: number | null;
  judge_note: string | null;
  passed: boolean | null;
  retrieval_ms: number;
  answer_ms: number | null;
  error: string | null;
}

export interface EvalRunDetail extends EvalRun {
  results: EvalResult[];
}

export interface EvalRunIn {
  eval_set_id: number;
  profile_id?: number;
  mode: RetrievalMode;
  top_k?: number;
  answers: boolean;
  judge: boolean;
  repair_citations: boolean;
  glossary: boolean;
  rerank: boolean;
  label?: string;
}

export interface EvalCompareSide {
  result_id: number;
  first_relevant_rank: number | null;
  top_source: string | null;
  answer: string | null;
  not_found: boolean | null;
  missing_facts: string[][] | null;
  cited_sources: string[] | null;
  faithfulness: number | null;
  passed: boolean | null;
  error: string | null;
}

export type EvalChange = "fixed" | "broken" | "better" | "worse" | "same" | "only_a" | "only_b";

export interface EvalCompareRow {
  case_id: number | null;
  question: string;
  shelf: string | null;
  kind: string;
  variant_group: string | null;
  expect_not_found: boolean;
  a: EvalCompareSide | null;
  b: EvalCompareSide | null;
  change: EvalChange;
}

export interface EvalCompare {
  a: EvalRun;
  b: EvalRun;
  same_index: boolean;
  cases: EvalCompareRow[];
}

export interface EvalDemoStatus {
  available: boolean;
  loaded_set_id: number | null;
}

// --- Glossary (decision 0021) -------------------------------------------------

export interface GlossaryTerm {
  id: number;
  term: string;
  means: string;
  created_at: string;
}
