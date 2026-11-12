import { Download, ExternalLink, FileText, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { API_BASE } from "@/api/client";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Document } from "@/api/types";
import { EmptyState, ErrorNote, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useCollections,
  useDeleteDocument,
  useJobs,
  useRestoreDocument,
  useDocuments,
  useReindexDocument,
} from "@/hooks/queries";
import { UploadFlow } from "@/components/library/UploadFlow";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { Paused } from "@/components/Paused";
import { cn, formatDate } from "@/lib/utils";

export default function Library() {
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const [trashed, setTrashed] = useState(false);
  const documents = useDocuments({ q: search.trim() || undefined, tag: tag || undefined, trashed });
  const collections = useCollections();
  const remove = useDeleteDocument();
  const restore = useRestoreDocument();
  const system = useSystemStatus();
  const [queued, setQueued] = useState<number[]>([]);
  const reindex = useReindexDocument();

  const collectionName = (id: number) =>
    collections.data?.find((c) => c.id === id)?.name ?? `#${id}`;

  return (
    <>
      <PageHeader
        title="Library"
        description="Add PDF, Word, Markdown or text files, or whole folders. You review what will happen to each file before anything is processed."
      />
      <div className="space-y-6 px-8 py-6">
        <Paused reason={system.processBlocked} what="Uploading documents">
          <UploadFlow onQueued={(ids) => setQueued((q) => [...q, ...ids])} />
          {queued.length > 0 && <UploadProgress jobIds={queued} onDone={() => setQueued([])} />}
        </Paused>

        <div className="flex flex-wrap items-center gap-2">
          <Input
            placeholder="Search by filename"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />
          {tag && (
            <Badge variant="secondary" className="cursor-pointer" onClick={() => setTag("")}>
              tag: {tag} ✕
            </Badge>
          )}
          <div className="ml-auto flex rounded-md border p-0.5 text-sm">
            {[false, true].map((value) => (
              <button
                key={String(value)}
                type="button"
                onClick={() => setTrashed(value)}
                className={cn(
                  "rounded px-3 py-1",
                  trashed === value ? "bg-muted font-medium" : "text-muted-foreground",
                )}
              >
                {value ? "Trash" : "Documents"}
              </button>
            ))}
          </div>
        </div>

        <ErrorNote error={documents.error ?? remove.error ?? reindex.error ?? restore.error} />
        {reindex.isSuccess && (
          <p className="text-sm text-muted-foreground">
            Reindex queued. Follow it in the <Link to="/queue" className="underline">queue</Link>.
          </p>
        )}

        {documents.data?.length === 0 ? (
          <EmptyState>
            {trashed
              ? "The trash is empty. Deleted documents stay here for 30 days."
              : search || tag
                ? "No documents match."
                : "No documents yet. Drop files above to index them."}
          </EmptyState>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">File</th>
                  <th className="px-4 py-2 font-medium">Collection</th>
                  <th className="px-4 py-2 font-medium">Version</th>
                  <th className="px-4 py-2 font-medium">{trashed ? "Deleted" : "Added"}</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {documents.data?.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    doc={doc}
                    collection={collectionName(doc.collection_id)}
                    onTag={setTag}
                    onReindex={() => reindex.mutate(doc.id)}
                    reindexBlocked={system.processBlocked}
                    onRestore={() => restore.mutate(doc.id)}
                    onDelete={() => {
                      if (confirm(`Move "${doc.filename}" to the trash? It is kept for 30 days.`)) {
                        remove.mutate(doc.id);
                      }
                    }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function DocumentRow({
  doc,
  collection,
  onTag,
  onReindex,
  onRestore,
  onDelete,
  reindexBlocked,
}: {
  reindexBlocked: string | null;
  doc: Document;
  collection: string;
  onTag: (tag: string) => void;
  onReindex: () => void;
  onRestore: () => void;
  onDelete: () => void;
}) {
  const isTrashed = doc.trashed_at !== null;
  return (
    <tr>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 font-medium">
          <FileText className="size-4 text-muted-foreground" />
          {doc.filename}
        </div>
        {doc.tags.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1 pl-6">
            {doc.tags.map((t) => (
              <Badge key={t} variant="secondary" className="cursor-pointer" onClick={() => onTag(t)}>
                {t}
              </Badge>
            ))}
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-muted-foreground">{collection}</td>
      <td className="px-4 py-3">
        v{doc.active_version_number ?? "–"}
        {doc.version_count > 1 && (
          <span className="text-muted-foreground"> of {doc.version_count}</span>
        )}
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
        {formatDate(isTrashed ? doc.trashed_at : doc.created_at)}
      </td>
      <td className="px-4 py-3 text-right">
        {isTrashed && (
          <Button variant="outline" size="sm" title="Take it out of the trash" onClick={onRestore}>
            <RotateCcw /> Restore
          </Button>
        )}
        {!isTrashed && (
          <div className="flex justify-end gap-1">
            <OpenOriginal doc={doc} />
            <Button
              variant="ghost"
              size="icon"
              title={reindexBlocked ? `Reindex is paused: ${reindexBlocked}` : "Reindex"}
              onClick={onReindex}
              disabled={!!reindexBlocked}
            >
              <RefreshCw />
            </Button>
            <Button variant="ghost" size="icon" title="Move to trash" onClick={onDelete}>
              <Trash2 />
            </Button>
          </div>
        )}
      </td>
    </tr>
  );
}

/** The file exactly as it was uploaded: PDFs and text open in a tab, Word files download. */
function OpenOriginal({ doc }: { doc: Document }) {
  const isWord = /\.docx$/i.test(doc.filename);
  return (
    <Button variant="ghost" size="icon" asChild title={isWord ? "Download the original (Word)" : "Open the original in a new tab"}>
      <a href={`${API_BASE}/documents/${doc.id}/original`} target={isWord ? undefined : "_blank"} rel="noreferrer">
        {isWord ? <Download /> : <ExternalLink />}
      </a>
    </Button>
  );
}

/** Follows the jobs of one upload: "2 of 3 done, 1 skipped", then a short
 * summary that clears itself. Notes (e.g. why a file was skipped) are listed. */
export function UploadProgress({ jobIds, onDone }: { jobIds: number[]; onDone: () => void }) {
  const jobs = useJobs();
  const mine = (jobs.data ?? []).filter((j) => jobIds.includes(j.id));
  const finished = mine.filter((j) => ["completed", "failed", "cancelled"].includes(j.status));
  const skipped = mine.filter((j) => j.result?.status === "skipped_duplicate");
  const failed = mine.filter((j) => j.status === "failed");
  const allDone = mine.length === jobIds.length && finished.length === mine.length;

  useEffect(() => {
    if (!allDone || failed.length > 0) return;
    const timer = setTimeout(onDone, 8000);
    return () => clearTimeout(timer);
  }, [allDone, failed.length, onDone]);

  const n = jobIds.length;
  return (
    <div className="space-y-1 rounded-md border bg-muted/30 px-3 py-2 text-sm">
      <p>
        {allDone ? "Done: " : `Processing ${n} file${n === 1 ? "" : "s"}: `}
        {finished.length - skipped.length - failed.length} indexed
        {skipped.length > 0 && `, ${skipped.length} skipped`}
        {failed.length > 0 && `, ${failed.length} failed`}
        {!allDone && `, ${n - finished.length} to go`}.{" "}
        <Link to="/queue" className="underline">
          Open the queue
        </Link>
        {allDone && (
          <button type="button" className="ml-2 text-muted-foreground underline" onClick={onDone}>
            Dismiss
          </button>
        )}
      </p>
      {mine
        .filter((j) => j.note || j.error)
        .map((j) => (
          <p key={j.id} className={cn("text-xs", j.error ? "text-destructive" : "text-warning")}>
            {j.subject}: {j.note ?? j.error}
          </p>
        ))}
    </div>
  );
}
