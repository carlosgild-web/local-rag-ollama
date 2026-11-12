import { Archive, Check, Copy, Download, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { API_BASE } from "@/api/client";
import type { Backup } from "@/api/types";
import { EmptyState, ErrorNote, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { isActiveJob, useBackups, useCreateBackup, useDeleteBackup, useJobs } from "@/hooks/queries";
import { formatBytes, formatDate } from "@/lib/utils";

const KIND: Record<string, { label: string; variant: "default" | "secondary" | "warning" }> = {
  manual: { label: "Manual", variant: "default" },
  auto: { label: "Automatic", variant: "secondary" },
  "before-restore": { label: "Before a restore", variant: "warning" },
};

function plural(n: number | undefined, one: string, many = `${one}s`) {
  return n === undefined ? `? ${many}` : `${n} ${n === 1 ? one : many}`;
}

/** Backups (decision 0015): make one now, download, delete, and how to restore. */
export default function Backups() {
  const backups = useBackups();
  const create = useCreateBackup();
  const remove = useDeleteBackup();
  const jobs = useJobs();
  const [restoring, setRestoring] = useState<Backup | null>(null);
  const running = jobs.data?.find((j) => j.job_type === "backup" && isActiveJob(j));
  const failed = jobs.data?.find((j) => j.job_type === "backup" && j.status === "failed" && j.id === create.data?.job_id);

  return (
    <>
      <PageHeader
        title="Backups"
        description="Everything the app keeps (the database, the search index and your original files) in one zip file."
        actions={
          <Button onClick={() => create.mutate()} disabled={create.isPending || !!running}>
            {create.isPending || running ? <Loader2 className="animate-spin" /> : <Archive />}
            {running ? "Backing up…" : "Back up now"}
          </Button>
        }
      />
      <div className="space-y-6 px-8 py-6">
        <ErrorNote error={backups.error ?? create.error ?? remove.error} />
        {failed && <p className="text-sm text-destructive">The backup failed: {failed.error}</p>}
        <Card>
          <CardHeader>
            <CardTitle>How backups work</CardTitle>
            <CardDescription>
              A backup is made automatically once a day when the app starts, and the newest 7 are kept (BACKUP_KEEP). Backups
              you make here are kept until you delete them. They are stored on this computer, in the data folder under
              backups/: download one to keep a copy somewhere else. Indexing waits while a backup runs.
            </CardDescription>
          </CardHeader>
        </Card>

        {backups.data?.length === 0 ? (
          <EmptyState>No backups yet. Click Back up now to make the first one.</EmptyState>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">Made</th>
                  <th className="px-4 py-2 font-medium">Kind</th>
                  <th className="px-4 py-2 font-medium">Contents</th>
                  <th className="px-4 py-2 font-medium">Size</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {backups.data?.map((b) => {
                  const m = b.manifest;
                  const kind = KIND[m?.reason ?? ""] ?? { label: m?.reason ?? "?", variant: "secondary" as const };
                  return (
                    <tr key={b.name}>
                      <td className="whitespace-nowrap px-4 py-3">
                        <div className="font-medium">{m ? formatDate(m.created_at) : b.name}</div>
                        <div className="font-mono text-xs text-muted-foreground">{b.name}</div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={kind.variant}>{kind.label}</Badge>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {b.error ? (
                          <span className="text-destructive">{b.error}</span>
                        ) : (
                          <>
                            {plural(m?.counts.documents, "document")} · {plural(m?.counts.shelves, "shelf", "shelves")} ·{" "}
                            {plural(m?.counts.chats, "chat")}
                            <div className="text-xs">app {m?.app_version}</div>
                          </>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{formatBytes(b.size)}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" size="icon" asChild title="Download">
                            <a href={`${API_BASE}/backups/${b.name}`} download>
                              <Download />
                            </a>
                          </Button>
                          <Button variant="ghost" size="icon" title="How to restore it" onClick={() => setRestoring(b)} disabled={!!b.error}>
                            <RotateCcw />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Delete"
                            onClick={() => {
                              if (confirm(`Delete the backup ${b.name}? This can't be undone.`)) remove.mutate(b.name);
                            }}
                          >
                            <Trash2 />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <RestoreDialog backup={restoring} onClose={() => setRestoring(null)} />
    </>
  );
}

function RestoreDialog({ backup, onClose }: { backup: Backup | null; onClose: () => void }) {
  if (!backup) return null;
  const commands = [
    { label: "Windows", command: `.\\start.cmd restore ${backup.name}` },
    { label: "macOS / Linux", command: `./start.sh restore ${backup.name}` },
    { label: "By hand (app stopped)", command: `python -m app.cli restore ${backup.name}` },
  ];
  return (
    <Dialog
      open
      onClose={onClose}
      title="Restore this backup"
      description={`Made ${backup.manifest ? formatDate(backup.manifest.created_at) : ""} · ${plural(backup.manifest?.counts.documents, "document")}`}
    >
      <div className="space-y-3 text-sm">
        <p>
          Restoring replaces everything (documents, versions, chats and settings) with this backup. It runs while the app
          is stopped, so it can't be started from this page. In the project folder, run:
        </p>
        {commands.map((c) => (
          <CommandLine key={c.label} label={c.label} command={c.command} />
        ))}
        <p className="text-muted-foreground">
          The start script stops the app, <b className="text-foreground">backs up the current data first</b> (a "Before a
          restore" backup), restores this one and starts the app again.
        </p>
      </div>
    </Dialog>
  );
}

function CommandLine({ label, command }: { label: string; command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{label}</p>
      <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 font-mono text-xs">
        <span className="flex-1 break-all">{command}</span>
        <Button
          variant="ghost"
          size="icon"
          className="size-7"
          title="Copy"
          onClick={() => {
            navigator.clipboard?.writeText(command).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          {copied ? <Check /> : <Copy />}
        </Button>
      </div>
    </div>
  );
}
