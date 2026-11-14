import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api, type DocumentFilters } from "@/api/client";
import type { AuditFilters, CollectionCreate, CollectionReindex, InspectIn, Job } from "@/api/types";

export const keys = {
  health: ["health"] as const,
  documents: (filters: DocumentFilters) => ["documents", filters] as const,
  collections: (includeInactive: boolean) => ["collections", includeInactive] as const,
  jobs: ["jobs"] as const,
  sessions: ["sessions"] as const,
  portalSessions: ["sessions", "intranet"] as const,
  session: (id: number) => ["session", id] as const,
  models: ["models"] as const,
  profiles: ["profiles"] as const,
  demo: ["demo"] as const,
};

const ACTIVE: Job["status"][] = ["pending", "running"];
export const isActiveJob = (job: Job) => ACTIVE.includes(job.status);

/** The troubleshooter; runs only while its panel is open. */
export function useDiagnostics(enabled: boolean) {
  return useQuery({
    queryKey: ["diagnostics"],
    queryFn: api.diagnostics,
    enabled,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
}

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: api.health, refetchInterval: 10_000 });
}

/** Polls fast while work is queued, slowly otherwise. When a job finishes,
 * documents and collections are refetched so the library catches up. */
export function useJobs() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: keys.jobs,
    queryFn: api.jobs,
    refetchInterval: (q) => (q.state.data?.some(isActiveJob) ? 1_500 : 5_000),
  });

  const activeIds = useRef<Set<number>>(new Set());
  useEffect(() => {
    if (!query.data) return;
    const nowActive = new Set(query.data.filter(isActiveJob).map((j) => j.id));
    const finished = [...activeIds.current].some((id) => !nowActive.has(id));
    activeIds.current = nowActive;
    if (finished) {
      client.invalidateQueries({ queryKey: ["documents"] });
      client.invalidateQueries({ queryKey: ["collections"] });
    }
  }, [query.data, client]);

  return query;
}

export function useDocuments(filters: DocumentFilters = {}) {
  return useQuery({ queryKey: keys.documents(filters), queryFn: () => api.documents(filters) });
}

export function useCollections(includeInactive = false) {
  return useQuery({
    queryKey: keys.collections(includeInactive),
    queryFn: () => api.collections(includeInactive),
  });
}

/** The console's chats; `q` keeps only chats with that text. */
export function useSessions(q = "") {
  return useQuery({ queryKey: [...keys.sessions, "admin", q], queryFn: () => api.sessions("admin", q) });
}

/** Questions asked in the employee portal, for the dashboard. */
export function usePortalSessions() {
  return useQuery({ queryKey: keys.portalSessions, queryFn: () => api.sessions("intranet") });
}

export function useSession(id: number | null) {
  return useQuery({
    queryKey: keys.session(id ?? 0),
    queryFn: () => api.session(id as number),
    enabled: id !== null,
  });
}

export function useModels() {
  return useQuery({ queryKey: keys.models, queryFn: api.models, retry: false });
}

/** The retrieval inspector. Keeps the last result on screen while the next
 * one loads, so the table doesn't flash as a slider moves; a superseded
 * request is aborted. */
export function useInspect(body: InspectIn | null) {
  return useQuery({
    queryKey: ["inspect", body],
    queryFn: ({ signal }) => api.inspect(body as InspectIn, signal),
    enabled: body !== null,
    placeholderData: (prev) => prev,
    staleTime: 30_000,
    retry: false,
  });
}

export function useProfiles() {
  return useQuery({ queryKey: keys.profiles, queryFn: api.profiles });
}

function useInvalidate() {
  const client = useQueryClient();
  return (...prefixes: string[]) =>
    Promise.all(prefixes.map((p) => client.invalidateQueries({ queryKey: [p] })));
}

export function useUpload() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (args: { files: File[]; collectionId?: number; tags?: string }) =>
      api.upload(args.files, { collectionId: args.collectionId, tags: args.tags }),
    onSuccess: () => invalidate("jobs"),
  });
}

export function useDeleteDocument() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: api.deleteDocument,
    onSuccess: () => invalidate("documents", "collections"),
  });
}

export function useRestoreDocument() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: api.restoreDocument,
    onSuccess: () => invalidate("documents", "collections"),
  });
}

/** A citation's passage; fetched only when someone opens it. */
export function useChunk(id: number | null) {
  return useQuery({
    queryKey: ["chunk", id],
    queryFn: () => api.chunk(id as number),
    enabled: id !== null,
    staleTime: Number.POSITIVE_INFINITY, // passages never change
  });
}

export function useReindexDocument() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.reindexDocument, onSuccess: () => invalidate("jobs") });
}

export function useCreateCollection() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: CollectionCreate) => api.createCollection(body),
    onSuccess: () => invalidate("collections"),
  });
}

export function useSetPortalVisible() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (args: { id: number; visible: boolean }) => api.setPortalVisible(args.id, args.visible),
    onSuccess: () => invalidate("collections"),
  });
}

export function useReindexCollection() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (args: { id: number; body?: CollectionReindex }) =>
      api.reindexCollection(args.id, args.body),
    onSuccess: () => invalidate("jobs", "collections"),
  });
}

export function useRetryJob() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.retryJob, onSuccess: () => invalidate("jobs") });
}

export function useCancelJob() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.cancelJob, onSuccess: () => invalidate("jobs") });
}

export function useFeedback(sessionId: number | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (args: { messageId: number; thumbsUp: boolean; comment?: string }) =>
      api.feedback(args.messageId, args.thumbsUp, args.comment),
    onSuccess: () => {
      if (sessionId !== null) client.invalidateQueries({ queryKey: keys.session(sessionId) });
      client.invalidateQueries({ queryKey: ["feedback"] });
    },
  });
}

/** The demo company offer on the dashboard; polls while it's loading. */
export function useDemo() {
  return useQuery({
    queryKey: keys.demo,
    queryFn: api.demo,
    refetchInterval: (q) => (q.state.data?.job && isActiveJob(q.state.data.job) ? 1_500 : false),
  });
}

export function useSeedDemo() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.seedDemo, onSuccess: () => invalidate("demo", "jobs") });
}

/** The demo company's original documents; fetched when the list is opened. */
export function useDemoFiles(enabled: boolean) {
  return useQuery({ queryKey: ["demo", "files"], queryFn: api.demoFiles, enabled, staleTime: Infinity });
}

/** A document's versions, newest first. */
export function useVersions(docId: number | null) {
  return useQuery({
    queryKey: ["versions", docId],
    queryFn: () => api.versions(docId as number),
    enabled: docId !== null,
  });
}

/** A version's searchable text; `editable` gives a text or Markdown file as written. */
export function useVersionText(docId: number, versionId: number, editable = false) {
  return useQuery({
    queryKey: ["version-text", docId, versionId, editable],
    queryFn: () => api.versionText(docId, versionId, editable),
    staleTime: Infinity,
  });
}

export function useDiff(docId: number, a: number, b: number) {
  return useQuery({ queryKey: ["diff", docId, a, b], queryFn: () => api.diff(docId, a, b), staleTime: Infinity });
}

/** Makes an earlier version the active one again (nothing is re-embedded). */
export function useRollback(docId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (versionId: number) => api.rollback(docId, versionId),
    onSuccess: () => invalidate("versions", "documents"),
  });
}

export function useFeedbackSummary() {
  return useQuery({ queryKey: ["feedback", "summary"], queryFn: api.feedbackSummary });
}

/** Saves edited text as a new version; returns the queued job. */
export function useEditText(docId: number) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { text: string; edited_by: string; note?: string }) => api.editText(docId, body),
    onSuccess: () => invalidate("jobs"),
  });
}

/** Backups, refreshed while a backup job runs. */
export function useBackups() {
  const jobs = useJobs();
  const busy = jobs.data?.some((j) => j.job_type === "backup" && isActiveJob(j));
  return useQuery({ queryKey: ["backups", busy], queryFn: api.backups, refetchInterval: busy ? 2_000 : false });
}

export function useAudit(filters: AuditFilters) {
  return useQuery({ queryKey: ["audit", filters], queryFn: () => api.audit(filters), placeholderData: (prev) => prev });
}

/** Delete permanently from the trash; the job's end refreshes the library (useJobs). */
export function usePurgeDocument() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.purgeDocument, onSuccess: () => invalidate("jobs", "audit") });
}

export function useCreateBackup() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.createBackup, onSuccess: () => invalidate("jobs", "backups") });
}

export function useDeleteBackup() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: api.deleteBackup, onSuccess: () => invalidate("backups") });
}

// --- Evaluation (decision 0019) ---------------------------------------------

const isActiveRun = (status: string) => status === "pending" || status === "running";

export function useEvalSets() {
  return useQuery({ queryKey: ["eval", "sets"], queryFn: api.evalSets });
}

export function useEvalSet(id: number | null) {
  return useQuery({
    queryKey: ["eval", "set", id],
    queryFn: () => api.evalSet(id as number),
    enabled: id !== null,
  });
}

export function useEvalOptions() {
  return useQuery({ queryKey: ["eval", "options"], queryFn: api.evalOptions });
}

export function useEvalDemo() {
  return useQuery({ queryKey: ["eval", "demo"], queryFn: api.evalDemo });
}

/** Polls while a run waits or runs, so progress and results come in. */
export function useEvalRuns(setId: number | null) {
  return useQuery({
    queryKey: ["eval", "runs", setId],
    queryFn: () => api.evalRuns(setId as number),
    enabled: setId !== null,
    refetchInterval: (q) => (q.state.data?.some((r) => isActiveRun(r.status)) ? 2_000 : false),
  });
}

export function useEvalRun(id: number | null) {
  return useQuery({
    queryKey: ["eval", "run", id],
    queryFn: () => api.evalRun(id as number),
    enabled: id !== null,
    refetchInterval: (q) => (q.state.data && isActiveRun(q.state.data.status) ? 3_000 : false),
  });
}

export function useEvalCompare(a: number | null, b: number | null) {
  return useQuery({
    queryKey: ["eval", "compare", a, b],
    queryFn: () => api.evalCompare(a as number, b as number),
    enabled: a !== null && b !== null,
  });
}

export function useEvalMutation<A, R>(mutationFn: (args: A) => Promise<R>) {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn, onSuccess: () => invalidate("eval", "jobs", "audit") });
}

// --- Glossary (decision 0021) -------------------------------------------------

export function useGlossary() {
  return useQuery({ queryKey: ["glossary"], queryFn: api.glossary });
}

export function useGlossaryMutation<A, R>(mutationFn: (args: A) => Promise<R>) {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn, onSuccess: () => invalidate("glossary", "audit") });
}
