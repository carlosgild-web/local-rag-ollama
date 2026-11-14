import { FolderPlus, Pause, Play, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import type { WatchedFolder, WatchScan } from "@/api/types";
import { EmptyState, ErrorNote, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useCollections, useWatchedFolderMutation, useWatchedFolders } from "@/hooks/queries";
import { formatDate } from "@/lib/utils";

const STATE: Record<WatchedFolder["state"], { label: string; variant: "success" | "secondary" | "destructive" | "warning" }> = {
  watching: { label: "Watching", variant: "success" },
  starting: { label: "Starting…", variant: "secondary" },
  paused: { label: "Paused", variant: "secondary" },
  error: { label: "Can't watch", variant: "destructive" },
  stopped: { label: "Watcher off", variant: "warning" },
};

export default function WatchedFolders() {
  const folders = useWatchedFolders();
  const data = folders.data;
  const [removing, setRemoving] = useState<WatchedFolder | null>(null);

  return (
    <>
      <PageHeader
        title="Watched folders"
        description="New and changed files in these folders are added to a shelf by themselves, with the same versioning as an upload."
      />
      <div className="space-y-6 px-8 py-6">
        <AddFolder />
        <ErrorNote error={folders.error} />
        {data && (
          <p className="text-xs text-muted-foreground">
            {data.mode === "polling"
              ? `Polling: each folder is checked every ${data.poll_seconds} s (WATCH_POLLING=true, for Docker and network drives).`
              : "File events from the operating system. Set WATCH_POLLING=true for Docker bind mounts or network drives."}{" "}
            A file is added once it stops changing for a couple of seconds. Deleting a file from a folder keeps its document;
            remove it in the <Link to="/library" className="underline">Library</Link> if you want it gone.
          </p>
        )}
        {data && data.folders.length === 0 && <EmptyState>No folders watched yet.</EmptyState>}
        {data?.folders.map((f) => (
          <FolderRow key={f.id} folder={f} onRemove={() => setRemoving(f)} />
        ))}
      </div>
      <RemoveDialog key={removing?.id ?? "none"} folder={removing} onClose={() => setRemoving(null)} />
    </>
  );
}

function AddFolder() {
  const collections = useCollections();
  const shelves = collections.data ?? [];
  const [path, setPath] = useState("");
  const [shelf, setShelf] = useState<string>("");
  const [recursive, setRecursive] = useState(true);
  const add = useWatchedFolderMutation((body: { path: string; collection_id: number; recursive: boolean }) =>
    api.addWatchedFolder(body),
  );
  const shelfId = shelf || (shelves[0] ? String(shelves[0].id) : "");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Watch a folder</CardTitle>
        <CardDescription>
          The full path on the machine running the app, such as <code>C:\Users\you\Documents\Policies</code>. In Docker
          it's the path inside the container: <code>/watch</code> is the <code>inbox</code> folder next to{" "}
          <code>compose.yaml</code>. The files already there are added once.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {collections.isSuccess && shelves.length === 0 ? (
          <p className="text-sm text-warning">
            Create a shelf first on the <Link to="/collections" className="underline">Collections</Link> page.
          </p>
        ) : (
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              add.mutate(
                { path: path.trim(), collection_id: Number(shelfId), recursive },
                { onSuccess: () => setPath("") },
              );
            }}
          >
            <label className="min-w-72 flex-1 space-y-1 text-sm">
              <span className="font-medium">Folder</span>
              <Input value={path} onChange={(e) => setPath(e.target.value)} placeholder="C:\Docs\Policies or /watch" />
            </label>
            <label className="space-y-1 text-sm">
              <span className="font-medium">Into shelf</span>
              <select
                className="block rounded-md border bg-background px-2 py-1.5"
                value={shelfId}
                onChange={(e) => setShelf(e.target.value)}
              >
                {shelves.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 pb-2 text-sm">
              <input type="checkbox" checked={recursive} onChange={(e) => setRecursive(e.target.checked)} />
              Include subfolders
            </label>
            <Button type="submit" disabled={!path.trim() || !shelfId || add.isPending}>
              <FolderPlus /> Watch
            </Button>
          </form>
        )}
        <ErrorNote error={add.error} />
      </CardContent>
    </Card>
  );
}

function FolderRow({ folder, onRemove }: { folder: WatchedFolder; onRemove: () => void }) {
  const update = useWatchedFolderMutation((enabled: boolean) => api.updateWatchedFolder(folder.id, { enabled }));
  const scan = useWatchedFolderMutation(() => api.scanWatchedFolder(folder.id));
  const [result, setResult] = useState<WatchScan | null>(null);
  const state = STATE[folder.state];

  return (
    <Card>
      <CardContent className="space-y-2 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-sm font-medium" title={folder.path}>
              {folder.path}
            </p>
            <p className="text-xs text-muted-foreground">
              Into <span className="font-medium text-foreground">{folder.collection_name}</span>
              {folder.recursive ? ", with subfolders" : ", top level only"} · {folder.files_queued} file
              {folder.files_queued === 1 ? "" : "s"} added
              {folder.last_file_at && `, the last ${formatDate(folder.last_file_at)}`}
              {folder.last_scan_at && ` · scanned ${formatDate(folder.last_scan_at)}`}
            </p>
          </div>
          <Badge variant={state.variant}>{state.label}</Badge>
          <Button
            variant="outline"
            size="sm"
            disabled={scan.isPending || !folder.enabled}
            onClick={() => scan.mutate(undefined, { onSuccess: setResult })}
            title="Add every file whose content isn't in the library yet"
          >
            <RefreshCw className={scan.isPending ? "animate-spin" : undefined} /> Scan now
          </Button>
          <Button variant="ghost" size="sm" disabled={update.isPending} onClick={() => update.mutate(!folder.enabled)}>
            {folder.enabled ? (
              <>
                <Pause /> Pause
              </>
            ) : (
              <>
                <Play /> Resume
              </>
            )}
          </Button>
          <Button variant="ghost" size="sm" onClick={onRemove} aria-label={`Stop watching ${folder.path}`}>
            <Trash2 />
          </Button>
        </div>
        {folder.state === "stopped" && (
          <p className="text-xs text-warning">
            The watcher isn't running in this server process, so only "Scan now" adds files.
          </p>
        )}
        {folder.error && <ErrorNote error={folder.error} />}
        <ErrorNote error={scan.error ?? update.error} />
        {result && (
          <p className="text-xs text-muted-foreground">
            Scan: {result.queued} file{result.queued === 1 ? "" : "s"} queued, {result.known} already in the library
            {result.skipped > 0 && `, ${result.skipped} skipped (empty, too large or unreadable)`}.{" "}
            {result.queued > 0 && (
              <Link to="/queue" className="underline">
                See the queue
              </Link>
            )}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function RemoveDialog({ folder, onClose }: { folder: WatchedFolder | null; onClose: () => void }) {
  const remove = useWatchedFolderMutation((id: number) => api.removeWatchedFolder(id));
  if (!folder) return null;
  return (
    <Dialog
      open
      onClose={onClose}
      title="Stop watching this folder?"
      description={folder.path}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate(folder.id, { onSuccess: onClose })}>
            Stop watching
          </Button>
        </>
      }
    >
      <p className="text-sm text-muted-foreground">
        The {folder.files_queued} document{folder.files_queued === 1 ? "" : "s"} it added stay on the shelf {folder.collection_name},
        and the folder's files aren't touched.
      </p>
      <ErrorNote error={remove.error} />
    </Dialog>
  );
}
