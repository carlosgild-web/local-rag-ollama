import { useQuery } from "@tanstack/react-query";
import { FileText, FolderOpen, Loader2, Play, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api } from "@/api/client";
import type { UploadCheckResult } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCollections } from "@/hooks/queries";
import { cn, formatBytes } from "@/lib/utils";
import { ReviewDialog } from "./ReviewDialog";

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
  /** Tag from the first folder below the chosen one, e.g. "HR". */
  folderTag: string | null;
}

const LAST_SHELF = "library.lastShelf";

/** Review-before-processing upload: pick files or a folder, unselect what
 * you don't want, review what will happen to each file, then process. */
export function UploadFlow({ onQueued }: { onQueued: (jobIds: number[]) => void }) {
  const rules = useQuery({ queryKey: ["upload-rules"], queryFn: api.uploadRules, staleTime: Number.POSITIVE_INFINITY });
  const collections = useCollections();
  const shelves = collections.data ?? [];
  const [items, setItems] = useState<PickedFile[]>([]);
  const [tags, setTags] = useState("");
  const [tagFolders, setTagFolders] = useState(false);
  const [shelf, setShelf] = useState<number | undefined>(() => {
    const stored = Number(localStorage.getItem(LAST_SHELF));
    return Number.isFinite(stored) && stored > 0 ? stored : undefined;
  });
  const [dragging, setDragging] = useState(false);
  const [hashing, setHashing] = useState<{ done: number; total: number } | null>(null);
  const [review, setReview] = useState<{ files: PickedFile[]; results: UploadCheckResult[] } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const filesInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  const shelfId = shelves.some((c) => c.id === shelf) ? shelf : shelves.length === 1 ? shelves[0].id : undefined;
  const needsShelf = shelves.length > 1 && shelfId === undefined;
  const selected = items.filter((i) => i.selected);

  const add = (incoming: { file: File; path: string }[]) => {
    if (!rules.data) return;
    setItems((current) => markSameNames(mergeFiles(current, incoming, rules.data.extensions, rules.data.max_upload_mb)));
  };

  const toggle = (key: string) =>
    setItems((list) => list.map((i) => (i.key === key && !i.problem ? { ...i, selected: !i.selected } : i)));
  const selectAll = (value: boolean) => setItems((list) => list.map((i) => ({ ...i, selected: value && !i.problem })));

  const process = async () => {
    setError(null);
    try {
      setHashing({ done: 0, total: selected.length });
      const hashes: Record<string, string> = {};
      for (const [index, item] of selected.entries()) {
        hashes[item.key] = await sha256(item.file);
        setHashing({ done: index + 1, total: selected.length });
      }
      const results = await api.checkUploads(
        shelfId,
        selected.map((i) => ({ name: i.file.name, sha256: hashes[i.key], size: i.file.size })),
      );
      setReview({ files: selected, results });
    } catch (e) {
      setError(e);
    } finally {
      setHashing(null);
    }
  };

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
            ? `${rules.data.extensions.map((e) => e.slice(1).toUpperCase()).join(", ")} · up to ${rules.data.max_upload_mb} MB each · nothing is processed until you confirm`
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
        <SelectionList
          items={items}
          onToggle={toggle}
          onSelectAll={selectAll}
          onClear={() => setItems([])}
          tagFolders={tagFolders}
        />
      )}

      {items.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          {shelves.length > 0 && (
            <label className={cn("flex items-center gap-1.5 text-sm", needsShelf && "text-warning")}>
              {needsShelf ? "Choose a shelf:" : "Shelf:"}
              <select
                className="h-9 rounded-md border border-input bg-background px-2 text-foreground"
                value={shelfId ?? ""}
                onChange={(e) => {
                  setShelf(Number(e.target.value));
                  localStorage.setItem(LAST_SHELF, e.target.value);
                }}
              >
                {shelfId === undefined && <option value="">—</option>}
                {shelves.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <Input
            placeholder="Tags for these files (comma-separated)"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            className="max-w-xs"
          />
          <label className="flex items-center gap-1.5 text-sm" title="e.g. files in the HR folder get the tag HR">
            <input type="checkbox" checked={tagFolders} onChange={(e) => setTagFolders(e.target.checked)} />
            Tag each file with its folder name
          </label>
          <Button className="ml-auto" onClick={process} disabled={selected.length === 0 || needsShelf || !!hashing}>
            {hashing ? <Loader2 className="animate-spin" /> : <Play />}
            {hashing ? `Checking ${hashing.done} of ${hashing.total}…` : `Process documents (${selected.length})`}
          </Button>
        </div>
      )}
      <ErrorNote error={error} />

      {review && (
        <ReviewDialog
          files={review.files}
          results={review.results}
          shelfId={shelfId}
          shelfName={shelves.find((c) => c.id === shelfId)?.name ?? "default"}
          tags={tags}
          tagFolders={tagFolders}
          onCancel={() => setReview(null)}
          onQueued={(jobIds, processedKeys, complete) => {
            // When everything chosen was sent, all reviewed files leave the list
            // (including duplicates and unticked ones). If an upload failed
            // part-way, only the sent files leave, so the rest can be retried.
            const gone = new Set(complete ? review.files.map((f) => f.key) : processedKeys);
            setReview(null);
            setItems((list) => list.filter((i) => !gone.has(i.key)));
            onQueued(jobIds);
          }}
        />
      )}
    </div>
  );
}

function SelectionList({
  items,
  onToggle,
  onSelectAll,
  onClear,
  tagFolders,
}: {
  items: PickedFile[];
  onToggle: (key: string) => void;
  onSelectAll: (value: boolean) => void;
  onClear: () => void;
  tagFolders: boolean;
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
                    {tagFolders && item.folderTag && (
                      <span className="ml-2 rounded-full bg-secondary px-2 py-0.5 text-xs">{item.folderTag}</span>
                    )}
                    {item.problem && <div className="text-xs text-destructive">{item.problem}</div>}
                    {!item.problem && item.sameNameAs && (
                      <div className="text-xs text-warning">
                        Same name as {item.sameNameAs}: on one shelf it would become a new version of it.
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
    const parts = path.split("/");
    added.push({
      key: `${path}:${file.size}:${file.lastModified}`,
      file,
      path,
      selected: !problem,
      problem,
      sameNameAs: null,
      folderTag: parts.length > 2 ? parts[1] : null, // root/<folder>/…/file
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

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
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
