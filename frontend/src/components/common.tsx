import { AlertCircle } from "lucide-react";
import type * as React from "react";
import type { JobStatus } from "@/api/types";
import { Badge } from "@/components/ui/badge";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b px-8 py-6">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span>{error instanceof Error ? error.message : String(error)}</span>
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed px-6 py-10 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

const JOB_VARIANT = {
  pending: "secondary",
  running: "default",
  completed: "success",
  failed: "destructive",
  cancelled: "outline",
} as const;

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return <Badge variant={JOB_VARIANT[status]}>{status}</Badge>;
}

export const JOB_LABEL: Record<string, string> = {
  ingest: "Ingest",
  reindex_document: "Reindex document",
  reindex_collection: "Reindex collection",
  rebuild_collection: "Rebuild collection",
  analyze_intake: "Suggest shelves",
  backup: "Backup",
  seed_demo: "Load demo company",
  run_eval: "Evaluation run",
  purge_trash: "Empty trash",
  purge_document: "Delete permanently",
};
