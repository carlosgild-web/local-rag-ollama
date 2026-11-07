import { useQuery } from "@tanstack/react-query";
import { FileText, FolderOpen, Loader2, Sparkles, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useCollections, useJobs } from "@/hooks/queries";
import { cn, formatBytes } from "@/lib/utils";
import { SuggestionsReview } from "./SuggestionsReview";

/** One file picked for upload, before anything is sent. */
export interface PickedFile {
  key: string;
  file: File;
  /** Path relative to the chosen folder, e.g. "HR/policy.docx". */
  path: string;
  selected: boolean;
  /** Why it can't be processed (unsupported, empty, too large), or null. */
  problem: string | null;
  /** Another picked file has the same name (it would become a version of it). */
  sameNameAs: string | null;
}

// The batch being analyzed or reviewed survives a page reload in this tab.
const BATCH_KEY = "library.intakeBatch";

function storedBatch(): { batchId: string; jobId: number } | null {
  try {
    return JSON.parse(sessionStorage.getItem(BATCH_KEY) ?? "null");
  } catch {
    return null;
  }
}

/** Upload with suggestions: pick files or a folder, unselect what you don't
 * want, let the app analyze them and suggest a shelf and tags for each, then
 * review, change anything and confirm. */
export function UploadFlow({ onQueued }: { onQueued: (jobIds: number[]) => void }) {
  const rules = useQuery({ queryKey: ["upload-rules"], queryFn: api.uploadRules, staleTime: Number.POSITIVE_INFINITY });
  const collections = useCollections();
  const jobs = useJobs();
  const [items, setItems] = useState<PickedFile[]>([]);
  const [dragging, setDragging] = useState(false);
  const [sending, setSending] = useState(false);
  const [batch, setBatch] = useState(storedBatch);
  const [error, setError] = useState<unknown>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  const selected = items.filter((i) => i.selected);
  const job = batch ? jobs.data?.find((j) => j.id === batch.jobId) : undefined;
  const intake = useQuery({
    queryKey: ["intake", batch?.batchId],
    queryFn: () => api.intake(batch?.batchId ?? ""),
    enabled: !!batch,
    retry: false,
    refetchInterval: (q) => (q.state.data?.state === "ready" ? false : 1_500),
  });

  useEffect(() => {
    if (batch) sessionStorage.setItem(BATCH_KEY, JSON.stringify(batch));
    else sessionStorage.removeItem(BATCH_KEY);
  }, [batch]);

  const add = (incoming: { file: File; path: string }[]) => {
    if (!rules.data) return;
    setItems((current) => markSameNames(mergeFiles(current, incoming, rules.data.extensions, rules.data.max_upload_mb)));
  };

  const toggle = (key: string) =>
    setItems((list) => list.map((i) => (i.key === key && !i.problem ? { ...i, selected: !i.selected } : i)));
  const selectAll = (value: boolean) => setItems((list) => list.map((i) => ({ ...i, selected: value && !i.problem })));

  const analyze = async () => {
    setError(null);
    setSending(true);
    try {
      const started = await api.startIntake(selected.map((i) => ({ file: i.file, path: i.path })));
      const sent = new Set(selected.map((i) => i.key));
      setItems((list) => list.filter((i) => !sent.has(i.key)));
      setBatch({ batchId: started.batch_id, jobId: started.job_id });
    } catch (e) {
      setError(e);
    } finally {
      setSending(false);
    }
  };

  const reset = () => setBatch(null);
  const discard = async () => {
    if (batch) await api.cancelIntake(batch.batchId).catch(() => undefined);
    reset();
  };

  if (batch) {
    if (intake.error) {
      // Expired or already processed (e.g. in another tab).
      return (
        <div className="space-y-2">
          <ErrorNote error={intake.error} />
          <Button variant="outline" onClick={reset}>
            Start over
          </Button>
        </div>
      );
    }
    if (intake.data?.state === "ready") {
      return (
        <SuggestionsReview
          batch={intake.data}
          existing={(collections.data ?? []).filter((c) => c.is_active)}
          onCancel={reset}
          onConfirmed={(jobIds) => {
            reset();
            onQueued(jobIds);
          }}
        />
      );
    }
    return <Analyzing job={job} files={intake.data?.files.length} onCancel={discard} />;
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={async (e) => {
          e.preventDefault();
          setDragging(false);
          add(await filesFromDrop(e.dataTransfer));
        }}
        className={cn(
          "flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-6 py-6 text-center transition-colors",
          dragging ? "border-primary bg-accent" : "border-border",
        )}
      >
        <Upload className="size-6 text-muted-foreground" />
        <p className="text-sm">Drop files or folders here, or</p>
        <div className="flex flex-wrap justify-center gap-2">
          <Button variant="outline" size="sm" onClick={() => filesInput.current?.click()} disabled={!rules.data}>
            <FileText /> Choose files…
          </Button>
          <Button variant="outline" size="sm" onClick={() => folderInput.current?.click()} disabled={!rules.data}>
            <FolderOpen /> Choose folder…
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          {rules.data
            ? `${rules.data.extensions.map((e) => e.slice(1).toUpperCase()).join(", ")} · up to ${rules.data.max_upload_mb} MB each · the app suggests a shelf and tags for each file, and nothing is processed until you confirm`
            : "Loading the upload rules…"}
        </p>
        <input
          ref={filesInput}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            add(Array.from(e.target.files ?? []).map((file) => ({ file, path: file.name })));
            e.target.value = "";
          }}
        />
        <input
          ref={folderInput}
          type="file"
          multiple
          className="hidden"
          // @ts-expect-error: webkitdirectory is a non-standard attribute every browser supports
          webkitdirectory=""
          onChange={(e) => {
            add(Array.from(e.target.files ?? []).map((file) => ({ file, path: file.webkitRelativePath || file.name })));
            e.target.value = "";
          }}
        />
      </div>

      {items.length > 0 && (
        <SelectionList items={items} onToggle={toggle} onSelectAll={selectAll} onClear={() => setItems([])} />
      )}

      {items.length > 0 && (
        <div className="flex justify-end">
          <Button onClick={analyze} disabled={selected.length === 0 || sending}>
            {sending ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {sending
              ? `Sending ${selected.length} file${selected.length === 1 ? "" : "s"} for analysis…`
              : `Analyze ${selected.length} document${selected.length === 1 ? "" : "s"}`}
          </Button>
        </div>
      )}
      <ErrorNote error={error} />
    </div>
  );
}

function Analyzing({
  job,
  files,
  onCancel,
}: {
  job: { status: string; progress: number; error: string | null } | undefined;
  files: number | undefined;
  onCancel: () => void;
}) {
  const failed = job?.status === "failed" || job?.status === "cancelled";
  const progress = job?.progress ?? 0;
  const step = job?.status === "pending"
    ? "Waiting for the job worker (other jobs may be running)…"
    : progress >= 0.8
      ? "Naming the suggested shelves (up to a minute)…"
      : progress >= 0.3
        ? "Comparing the documents with each other and with your shelves…"
        : files
          ? `Reading document ${Math.min(files, Math.floor((progress / 0.3) * files) + 1)} of ${files}…`
          : "Reading the documents…";
  return (
    <div className="space-y-3 rounded-lg border bg-card p-4 text-sm">
      <div className="flex items-center gap-2">
        {failed ? null : <Loader2 className="size-4 animate-spin text-primary" />}
        <span className="font-medium">{failed ? "The analysis didn't finish" : "Analyzing your documents"}</span>
      </div>
      {failed ? (
        <ErrorNote error={job?.error ?? "The analysis job stopped."} />
      ) : (
        <>
          <Progress value={progress} />
          <p className="text-muted-foreground">{step}</p>
        </>
      )}
      <Button variant="outline" size="sm" onClick={onCancel}>
        {failed ? "Discard and start over" : "Cancel"}
      </Button>
    </div>
  );
}

function SelectionList({
  items,
  onToggle,
  onSelectAll,
  onClear,
}: {
  items: PickedFile[];
  onToggle: (key: string) => void;
  onSelectAll: (value: boolean) => void;
  onClear: () => void;
}) {
  const selectable = items.filter((i) => !i.problem);
  const selectedCount = items.filter((i) => i.selected).length;
  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="flex flex-wrap items-center gap-3 border-b bg-muted/50 px-4 py-2 text-sm">
        <span className="font-medium">
          {items.length} file{items.length === 1 ? "" : "s"} · {selectedCount} selected
        </span>
        <button type="button" className="text-primary underline-offset-2 hover:underline" onClick={() => onSelectAll(true)}>
          Select all ({selectable.length})
        </button>
        <button type="button" className="text-primary underline-offset-2 hover:underline" onClick={() => onSelectAll(false)}>
          Select none
        </button>
        <Button variant="ghost" size="sm" className="ml-auto" onClick={onClear}>
          <Trash2 /> Clear list
        </Button>
      </div>
      <div className="max-h-80 overflow-y-auto">
        <table className="w-full text-sm">
          <tbody className="divide-y">
            {items.map((item) => {
              const folder = item.path.includes("/") ? item.path.slice(0, item.path.lastIndexOf("/") + 1) : "";
              return (
                <tr key={item.key} className={cn(item.problem && "opacity-60")}>
                  <td className="w-10 px-4 py-2">
                    <input
                      type="checkbox"
                      aria-label={`Include ${item.path}`}
                      checked={item.selected}
                      disabled={!!item.problem}
                      onChange={() => onToggle(item.key)}
                    />
                  </td>
                  <td className="py-2 pr-3">
                    <span className="text-muted-foreground">{folder}</span>
                    <span className="font-medium">{item.file.name}</span>
                    {item.problem && <div className="text-xs text-destructive">{item.problem}</div>}
                    {!item.problem && item.sameNameAs && (
                      <div className="text-xs text-warning">
                        Same name as {item.sameNameAs}: on the same shelf it would become a new version of it.
                        {item.selected ? "" : " Unselected; tick it if that's what you want."}
                      </div>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-right text-muted-foreground">
                    {formatBytes(item.file.size) === "—" ? "0 B" : formatBytes(item.file.size)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function mergeFiles(
  current: PickedFile[],
  incoming: { file: File; path: string }[],
  extensions: string[],
  maxMb: number,
): PickedFile[] {
  const known = new Set(current.map((i) => i.path));
  const added: PickedFile[] = [];
  for (const { file, path } of incoming) {
    if (known.has(path) || file.name.startsWith(".")) continue; // already listed, or a hidden system file
    known.add(path);
    const ext = file.name.includes(".") ? file.name.slice(file.name.lastIndexOf(".")).toLowerCase() : "";
    const problem = !extensions.includes(ext)
      ? `This file type can't be read (supported: ${extensions.join(", ")}).`
      : file.size === 0
        ? "The file is empty."
        : file.size > maxMb * 1024 * 1024
          ? `Larger than the ${maxMb} MB limit.`
          : null;
    added.push({
      key: `${path}:${file.size}:${file.lastModified}`,
      file,
      path,
      selected: !problem,
      problem,
      sameNameAs: null,
    });
  }
  return [...current, ...added];
}

/** Same file name twice: the first stays selected, the others are flagged
 * and unselected (on one shelf, a known name means "new version"). */
function markSameNames(items: PickedFile[]): PickedFile[] {
  const first = new Map<string, PickedFile>();
  return items.map((item) => {
    if (item.problem) return item;
    const name = item.file.name.toLowerCase();
    const earlier = first.get(name);
    if (!earlier) {
      first.set(name, item);
      return { ...item, sameNameAs: null };
    }
    const flaggedBefore = item.sameNameAs !== null;
    return { ...item, sameNameAs: earlier.path, selected: flaggedBefore ? item.selected : false };
  });
}

/** Files from a drop, including whole folders (walked recursively). */
async function filesFromDrop(data: DataTransfer): Promise<{ file: File; path: string }[]> {
  const entries = Array.from(data.items)
    .map((item) => item.webkitGetAsEntry?.())
    .filter((e): e is FileSystemEntry => !!e);
  if (entries.length === 0) return Array.from(data.files).map((file) => ({ file, path: file.name }));
  const out: { file: File; path: string }[] = [];
  const walk = async (entry: FileSystemEntry): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
      out.push({ file, path: entry.fullPath.replace(/^\//, "") });
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      // readEntries returns results in pages; keep reading until it returns none
      for (;;) {
        const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
        if (batch.length === 0) break;
        for (const child of batch) await walk(child);
      }
    }
  };
  for (const entry of entries) await walk(entry);
  return out;
}
