import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api, type DocumentFilters } from "@/api/client";
import type { CollectionCreate, CollectionReindex, Job } from "@/api/types";

export const keys = {
  health: ["health"] as const,
  documents: (filters: DocumentFilters) => ["documents", filters] as const,
  collections: (includeInactive: boolean) => ["collections", includeInactive] as const,
  jobs: ["jobs"] as const,
  sessions: ["sessions"] as const,
  session: (id: number) => ["session", id] as const,
  models: ["models"] as const,
  profiles: ["profiles"] as const,
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

export function useSessions() {
  return useQuery({ queryKey: keys.sessions, queryFn: api.sessions });
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
    mutationFn: (args: { messageId: number; thumbsUp: boolean }) =>
      api.feedback(args.messageId, args.thumbsUp),
    onSuccess: () => {
      if (sessionId !== null) client.invalidateQueries({ queryKey: keys.session(sessionId) });
    },
  });
}
