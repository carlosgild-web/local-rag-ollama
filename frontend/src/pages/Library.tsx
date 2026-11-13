import { ArrowDown, ArrowUp, ArrowUpDown, Download, ExternalLink, FileText, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import { API_BASE } from "@/api/client";
import { type ReactNode, useEffect, useState } from "react";
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
import { DocumentDetails } from "@/components/library/DocumentDetails";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { Paused } from "@/components/Paused";
import { cn, formatDate } from "@/lib/utils";

export default function Library() {
  const [search, setSearch] = useState("");
  const [tag, setTag] = useState("");
  const [trashed, setTrashed] = useState(false);
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  const [openId, setOpenId] = useState<number | null>(null);
  const documents = useDocuments({ q: search.trim() || undefined, tag: tag || undefined, trashed });
  const collections = useCollections();
  const remove = useDeleteDocument();
  const restore = useRestoreDocument();
  const system = useSystemStatus();
  const [queued, setQueued] = useState<number[]>([]);
  const reindex = useReindexDocument();

  const collectionName = (id: number) =>
    collections.data?.find((c) => c.id === id)?.name ?? `#${id}`;
  const showTrash = (value: boolean) => {
    setTrashed(value);
    setSort(value ? TRASH_SORT : DEFAULT_SORT);
  };
  const rows = sortDocuments(documents.data ?? [], sort, collectionName);
  const header = (key: SortKey, label: string) => (
    <SortableHeader sortKey={key} sort={sort} onSort={setSort}>
      {label}
    </SortableHeader>
  );
  const openDoc = documents.data?.find((d) => d.id === openId) ?? null;

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
                onClick={() => showTrash(value)}
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
                  {header("file", "File")}
                  {header("collection", "Collection")}
                  {header("version", "Version")}
                  {trashed ? header("deleted", "Deleted") : header("added", "Added")}
                  {!trashed && header("updated", "Updated")}
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    doc={doc}
                    onOpen={() => setOpenId(doc.id)}
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
      <DocumentDetails
        doc={openDoc}
        collection={openDoc ? collectionName(openDoc.collection_id) : ""}
        onClose={() => setOpenId(null)}
      />
    </>
  );
}

type SortKey = "file" | "collection" | "version" | "added" | "updated" | "deleted";
type Sort = { key: SortKey; dir: "asc" | "desc" };
/** Most recently changed first; documents with one version count from when they were added. */
const DEFAULT_SORT: Sort = { key: "updated", dir: "desc" };
const TRASH_SORT: Sort = { key: "deleted", dir: "desc" };
const TEXT_KEYS: SortKey[] = ["file", "collection"];

const byText = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });
const byDate = (a: string | null, b: string | null) => (a ? Date.parse(a) : 0) - (b ? Date.parse(b) : 0);

function sortDocuments(docs: Document[], sort: Sort, collectionName: (id: number) => string): Document[] {
  const compare = (a: Document, b: Document): number => {
    switch (sort.key) {
      case "file":
        return byText(a.filename, b.filename);
      case "collection":
        return byText(collectionName(a.collection_id), collectionName(b.collection_id));
      case "version":
        return (a.active_version_number ?? 0) - (b.active_version_number ?? 0) || a.version_count - b.version_count;
      case "added":
        return byDate(a.created_at, b.created_at);
      case "updated":
        return byDate(a.updated_at, b.updated_at);
      case "deleted":
        return byDate(a.trashed_at, b.trashed_at);
    }
  };
  const sign = sort.dir === "asc" ? 1 : -1;
  // Ties: newest document first, so the order never jumps between refreshes.
  return [...docs].sort((a, b) => sign * compare(a, b) || b.id - a.id);
}

/** A column header that sorts the table: first click picks the column, the next flips it. */
function SortableHeader({
  sortKey,
  sort,
  onSort,
  children,
}: {
  sortKey: SortKey;
  sort: Sort;
  onSort: (sort: Sort) => void;
  children: ReactNode;
}) {
  const active = sort.key === sortKey;
  const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  const next: Sort = active
    ? { key: sortKey, dir: sort.dir === "asc" ? "desc" : "asc" }
    : { key: sortKey, dir: TEXT_KEYS.includes(sortKey) ? "asc" : "desc" };
  return (
    <th className="px-4 py-2 font-medium" aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={() => onSort(next)}
        className={cn("inline-flex items-center gap-1 uppercase hover:text-foreground", active && "text-foreground")}
      >
        {children}
        <Icon className={cn("size-3", !active && "opacity-40")} />
      </button>
    </th>
  );
}

function DocumentRow({
  doc,
  onOpen,
  collection,
  onTag,
  onReindex,
  onRestore,
  onDelete,
  reindexBlocked,
}: {
  reindexBlocked: string | null;
  doc: Document;
  onOpen: () => void;
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
        <button
          type="button"
          onClick={onOpen}
          title="See its text, versions and changes"
          className="flex items-center gap-2 text-left font-medium hover:text-primary hover:underline"
        >
          <FileText className="size-4 text-muted-foreground" />
          {doc.filename}
        </button>
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
      {!isTrashed && (
        <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
          {doc.updated_at !== doc.created_at && doc.version_count > 1 ? formatDate(doc.updated_at) : "–"}
        </td>
      )}
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
