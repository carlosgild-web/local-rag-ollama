import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Play } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";
import type { UploadCheckResult, UploadCheckStatus } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { cn, formatDate } from "@/lib/utils";
import type { PickedFile } from "./UploadFlow";

const STATUS: Record<UploadCheckStatus, { label: string; variant: "success" | "default" | "secondary" | "warning" | "destructive"; include: boolean | null }> = {
  new: { label: "New", variant: "success", include: true },
  new_version: { label: "New version", variant: "default", include: true },
  name_in_trash: { label: "Name in trash", variant: "warning", include: true },
  duplicate: { label: "Already in library", variant: "secondary", include: null },
  unsupported: { label: "Can't be read", variant: "destructive", include: null },
  empty: { label: "Empty", variant: "destructive", include: null },
  too_large: { label: "Too large", variant: "destructive", include: null },
};
// include null: can't be processed (or would be skipped anyway), so it's not offered.

const BATCH = 10;

/** The confirmation step: what will happen to each file, adjustable, then
 * "Start processing" uploads the included files and queues their jobs. */
export function ReviewDialog({
  files,
  results,
  shelfId,
  shelfName,
  tags,
  tagFolders,
  onCancel,
  onQueued,
}: {
  files: PickedFile[];
  results: UploadCheckResult[];
  shelfId: number | undefined;
  shelfName: string;
  tags: string;
  tagFolders: boolean;
  onCancel: () => void;
  /** complete: every chosen file was sent. */
  onQueued: (jobIds: number[], processedKeys: string[], complete: boolean) => void;
}) {
  const client = useQueryClient();
  const rows = files.map((file, index) => ({ file, result: results[index] }));
  const [include, setInclude] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(rows.map(({ file, result }) => [file.key, STATUS[result.status].include === true])),
  );
  const [sending, setSending] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<unknown>(null);

  const counts = rows.reduce<Partial<Record<UploadCheckStatus, number>>>((acc, { result }) => {
    acc[result.status] = (acc[result.status] ?? 0) + 1;
    return acc;
  }, {});
  const chosen = rows.filter(({ file }) => include[file.key]);

  const start = async () => {
    setError(null);
    const groups = new Map<string, PickedFile[]>();
    for (const { file } of chosen) {
      const tagList = [tags, tagFolders && file.folderTag ? file.folderTag : ""].filter(Boolean).join(",");
      groups.set(tagList, [...(groups.get(tagList) ?? []), file]);
    }
    const jobIds: number[] = [];
    const processed: string[] = [];
    setSending({ done: 0, total: chosen.length });
    try {
      for (const [tagList, group] of groups) {
        for (let i = 0; i < group.length; i += BATCH) {
          const batch = group.slice(i, i + BATCH);
          const response = await api.upload(
            batch.map((f) => f.file),
            { collectionId: shelfId, tags: tagList || undefined },
          );
          jobIds.push(...response.jobs.map((j) => j.job_id));
          processed.push(...batch.map((f) => f.key));
          setSending({ done: processed.length, total: chosen.length });
        }
      }
      client.invalidateQueries({ queryKey: ["jobs"] });
      onQueued(jobIds, processed, true);
    } catch (e) {
      setError(e);
      if (jobIds.length) {
        client.invalidateQueries({ queryKey: ["jobs"] });
        onQueued(jobIds, processed, false); // keep what was already queued; the rest stays in the list
      }
    } finally {
      setSending(null);
    }
  };

  return (
    <Dialog
      open
      onClose={() => !sending && onCancel()}
      className="max-w-3xl"
      title="Review before processing"
      description={`Shelf "${shelfName}". Nothing has been uploaded yet; adjust the selection, then start.`}
      footer={
        <>
          <Button variant="outline" className="mr-auto" onClick={onCancel} disabled={!!sending}>
            <ArrowLeft /> Back to the list
          </Button>
          {chosen.length === 0 && !rows.some(({ result }) => STATUS[result.status].include !== null) ? (
            <Button onClick={() => onQueued([], [], true)}>Nothing to process: remove them from the list</Button>
          ) : (
            <Button onClick={start} disabled={chosen.length === 0 || !!sending}>
              {sending ? <Loader2 className="animate-spin" /> : <Play />}
              {sending
                ? `Uploading ${sending.done} of ${sending.total}…`
                : `Start processing ${chosen.length} document${chosen.length === 1 ? "" : "s"}`}
            </Button>
          )}
        </>
      }
    >
      <div className="mb-4 flex flex-wrap gap-2">
        {(Object.keys(STATUS) as UploadCheckStatus[])
          .filter((status) => counts[status])
          .map((status) => (
            <Badge key={status} variant={STATUS[status].variant}>
              {STATUS[status].label}: {counts[status]}
            </Badge>
          ))}
      </div>
      {(counts.duplicate ?? 0) > 0 && (
        <p className="mb-3 rounded-md border bg-muted/50 px-3 py-2 text-sm">
          Files already in the library are left out: the same content is never stored twice. To move a document to
          another shelf, delete it there first.
        </p>
      )}
      <ErrorNote error={error} />
      <ul className="divide-y rounded-md border text-sm">
        {rows.map(({ file, result }) => {
          const meta = STATUS[result.status];
          const offered = meta.include !== null;
          return (
            <li key={file.key} className={cn("flex items-start gap-3 px-3 py-2", !offered && "opacity-70")}>
              <input
                type="checkbox"
                className="mt-1"
                aria-label={`Process ${file.path}`}
                checked={!!include[file.key]}
                disabled={!offered || !!sending}
                onChange={(e) => setInclude((s) => ({ ...s, [file.key]: e.target.checked }))}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="break-all font-medium">{file.path}</span>
                  <Badge variant={meta.variant}>{meta.label}</Badge>
                </div>
                <p className="text-muted-foreground">
                  {result.message}
                  {result.existing_since && ` (${result.status === "name_in_trash" ? "deleted" : "since"} ${formatDate(result.existing_since)})`}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </Dialog>
  );
}
