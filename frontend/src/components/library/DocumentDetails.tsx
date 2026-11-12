import { useEffect, useState } from "react";
import { Download, ExternalLink, FileText, GitCompare, History, Loader2, Pencil, RotateCcw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE } from "@/api/client";
import type { Document, DocumentVersion } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { DiffLines } from "@/components/DiffLines";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { useDiff, useEditText, useJobs, useRollback, useVersionText, useVersions } from "@/hooks/queries";
import { cn, formatDate } from "@/lib/utils";

type Tab = "content" | "versions" | "compare";

/**
 * One document: the text the app searches (per version), its version history,
 * a comparison of any two versions, and restoring an earlier version.
 */
export function DocumentDetails({
  doc,
  collection,
  onClose,
}: {
  doc: Document | null;
  collection: string;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("content");
  const [viewId, setViewId] = useState<number | null>(null);
  const [pair, setPair] = useState<[number, number] | null>(null);
  const [editing, setEditing] = useState(false);
  const versions = useVersions(doc?.id ?? null);
  const list = versions.data ?? [];
  const active = list.find((v) => v.is_active);

  useEffect(() => {
    setTab("content");
    setViewId(null);
    setPair(null);
    setEditing(false);
  }, [doc?.id]);

  if (!doc) return null;
  const isWord = /\.docx$/i.test(doc.filename);
  const shownId = viewId ?? active?.id ?? null;
  const defaultPair: [number, number] | null =
    list.length >= 2 ? [list[1].id, (active ?? list[0]).id === list[1].id ? list[0].id : (active ?? list[0]).id] : null;

  return (
    <Dialog
      open
      side="right"
      onClose={onClose}
      className="max-w-2xl"
      title={doc.filename}
      description={
        <>
          Shelf <b>{collection}</b> · v{doc.active_version_number ?? "–"} of {doc.version_count} · added{" "}
          {formatDate(doc.created_at)} · updated {formatDate(doc.updated_at)}
        </>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border p-0.5 text-sm">
          {(
            [
              ["content", "Content", FileText],
              ["versions", `Versions (${list.length || doc.version_count})`, History],
              ["compare", "Compare", GitCompare],
            ] as const
          ).map(([key, label, Icon]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              disabled={key === "compare" && list.length < 2}
              className={cn(
                "flex items-center gap-1.5 rounded px-3 py-1 disabled:opacity-40",
                tab === key ? "bg-muted font-medium" : "text-muted-foreground",
              )}
            >
              <Icon className="size-3.5" /> {label}
            </button>
          ))}
        </div>
        <Button variant="outline" size="sm" asChild className="ml-auto">
          <a
            href={`${API_BASE}/documents/${doc.id}/original`}
            target={isWord ? undefined : "_blank"}
            rel="noreferrer"
            title="The active version's file, exactly as it was uploaded"
          >
            {isWord ? <Download /> : <ExternalLink />} Original
          </a>
        </Button>
      </div>
      <ErrorNote error={versions.error} />

      {tab === "content" && shownId !== null && !editing && (
        <ContentView
          docId={doc.id}
          versions={list}
          shownId={shownId}
          onPick={setViewId}
          onEdit={doc.trashed_at === null && shownId === active?.id ? () => setEditing(true) : undefined}
        />
      )}
      {tab === "content" && editing && active && (
        <EditView
          doc={doc}
          active={active}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            setViewId(null);
            setTab("versions");
          }}
        />
      )}
      {tab === "versions" && (
        <VersionList
          docId={doc.id}
          versions={list}
          onView={(id) => {
            setViewId(id);
            setTab("content");
          }}
          onCompare={(a, b) => {
            setPair([a, b]);
            setTab("compare");
          }}
        />
      )}
      {tab === "compare" && (pair ?? defaultPair) && (
        <CompareView docId={doc.id} versions={list} pair={(pair ?? defaultPair) as [number, number]} onPair={setPair} />
      )}
    </Dialog>
  );
}

function versionLabel(v: DocumentVersion) {
  return `v${v.version_number}${v.is_active ? " (active)" : ""} · ${formatDate(v.created_at)}`;
}

function ContentView({
  docId,
  versions,
  shownId,
  onPick,
  onEdit,
}: {
  docId: number;
  versions: DocumentVersion[];
  shownId: number;
  onPick: (id: number) => void;
  /** Only for the active version of a document that isn't in the trash. */
  onEdit?: () => void;
}) {
  const text = useVersionText(docId, shownId);
  return (
    <div className="mt-4 space-y-2">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">Text the app reads and searches, from</span>
        <select
          value={shownId}
          onChange={(e) => onPick(Number(e.target.value))}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {versionLabel(v)}
            </option>
          ))}
        </select>
        {onEdit && (
          <Button variant="outline" size="sm" className="ml-auto" onClick={onEdit} disabled={!text.data}>
            <Pencil /> Edit text
          </Button>
        )}
      </div>
      <ErrorNote error={text.error} />
      {text.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading the text…
        </p>
      ) : (
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-sans text-sm leading-relaxed">
          {text.data?.text || "(no text)"}
        </pre>
      )}
      {text.data && (
        <p className="text-xs text-muted-foreground">
          {text.data.text.length.toLocaleString()} characters. For PDFs and Word files this is the text taken out of the
          file; use Original to see the file itself.
        </p>
      )}
    </div>
  );
}

function VersionList({
  docId,
  versions,
  onView,
  onCompare,
}: {
  docId: number;
  versions: DocumentVersion[];
  onView: (id: number) => void;
  onCompare: (a: number, b: number) => void;
}) {
  const rollback = useRollback(docId);
  return (
    <div className="mt-4 space-y-3">
      <ErrorNote error={rollback.error} />
      <ol className="space-y-2">
        {versions.map((v, i) => {
          const previous = versions[i + 1];
          return (
            <li key={v.id} className={cn("rounded-md border p-3", v.is_active && "border-primary/50 bg-primary/5")}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">v{v.version_number}</span>
                {v.is_active && <Badge>Active: used for answers</Badge>}
                <span className="text-sm text-muted-foreground">
                  {formatDate(v.created_at)} · {v.ext.replace(".", "").toUpperCase()} · {v.chunk_count} passage{v.chunk_count === 1 ? "" : "s"}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {v.origin === "edit" ? (
                  <>
                    <Pencil className="mr-1 inline size-3.5" />
                    Edited in the app by <b className="text-foreground">{v.edited_by}</b>
                    {v.note ? <>: “{v.note}”</> : null}
                  </>
                ) : (
                  <>Uploaded{v.note ? ` · ${v.note}` : ""}</>
                )}
              </p>
              <div className="mt-2 flex flex-wrap gap-1">
                <Button variant="ghost" size="sm" onClick={() => onView(v.id)}>
                  <FileText /> View text
                </Button>
                {previous && (
                  <Button variant="ghost" size="sm" onClick={() => onCompare(previous.id, v.id)}>
                    <GitCompare /> Compare with v{previous.version_number}
                  </Button>
                )}
                {!v.is_active && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={rollback.isPending}
                    onClick={() => {
                      if (
                        confirm(
                          `Make v${v.version_number} the active version again? Answers will use its text right away. ` +
                            "Nothing is deleted: you can switch back at any time.",
                        )
                      ) {
                        rollback.mutate(v.id);
                      }
                    }}
                  >
                    {rollback.isPending ? <Loader2 className="animate-spin" /> : <RotateCcw />} Restore this version
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="text-xs text-muted-foreground">
        Restoring only switches which version answers use. No version is deleted, and nothing is processed again.
      </p>
    </div>
  );
}

function CompareView({
  docId,
  versions,
  pair,
  onPair,
}: {
  docId: number;
  versions: DocumentVersion[];
  pair: [number, number];
  onPair: (pair: [number, number]) => void;
}) {
  const [a, b] = pair;
  const diff = useDiff(docId, a, b);
  const picker = (value: number, set: (id: number) => void) => (
    <select
      value={value}
      onChange={(e) => set(Number(e.target.value))}
      className="rounded-md border bg-background px-2 py-1 text-sm"
    >
      {versions.map((v) => (
        <option key={v.id} value={v.id}>
          {versionLabel(v)}
        </option>
      ))}
    </select>
  );
  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">From</span>
        {picker(a, (id) => onPair([id, b]))}
        <span className="text-muted-foreground">to</span>
        {picker(b, (id) => onPair([a, id]))}
      </div>
      <ErrorNote error={diff.error} />
      {diff.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Comparing…
        </p>
      ) : (
        <DiffLines diff={diff.data?.diff ?? []} empty="The text is the same in both versions." />
      )}
    </div>
  );
}

const EDITOR_NAME_KEY = "rag-editor-name";

/** Edits the active version's text and saves it as a new version, marked with who
 * edited it and what changed. The original upload stays as an earlier version. */
function EditView({
  doc,
  active,
  onCancel,
  onSaved,
}: {
  doc: Document;
  active: DocumentVersion;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const current = useVersionText(doc.id, active.id, true);
  const edit = useEditText(doc.id);
  const jobs = useJobs();
  const client = useQueryClient();
  const [text, setText] = useState<string | null>(null);
  const [name, setName] = useState(() => {
    try {
      return localStorage.getItem(EDITOR_NAME_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const [note, setNote] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const value = text ?? current.data?.text ?? "";
  const job = jobs.data?.find((j) => j.id === jobId);
  const isBinary = /\.(pdf|docx)$/i.test(doc.filename);

  useEffect(() => {
    if (job?.status === "completed") {
      client.invalidateQueries({ queryKey: ["versions"] });
      client.invalidateQueries({ queryKey: ["documents"] });
      onSaved();
    }
  }, [job?.status, client, onSaved]);

  const save = () => {
    try {
      localStorage.setItem(EDITOR_NAME_KEY, name.trim());
    } catch {
      // storage blocked: the name just isn't remembered
    }
    edit.mutate(
      { text: value, edited_by: name.trim(), note: note.trim() || undefined },
      { onSuccess: (queued) => setJobId(queued.job_id) },
    );
  };
  const saving = edit.isPending || (job !== undefined && ["pending", "running"].includes(job.status));
  const changed = current.data !== undefined && value.trim() !== current.data.text.trim();

  return (
    <div className="mt-4 space-y-3">
      <p className="text-sm text-muted-foreground">
        Editing the text of v{active.version_number}. Saving makes it <b className="text-foreground">v{doc.version_count + 1}</b>, the
        version answers use; nothing is lost, and you can restore any earlier version.
        {isBinary
          ? " For PDF and Word files you edit the text the app searches; it's saved as a text file, and the original file stays in the earlier version."
          : " The file is saved in the same format, as you see it here."}
      </p>
      {current.isLoading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading the text…
        </p>
      ) : (
        <Textarea
          value={value}
          onChange={(e) => setText(e.target.value)}
          className="min-h-[45vh] font-mono text-xs leading-relaxed"
          aria-label="Document text"
          disabled={saving}
        />
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="space-y-1 text-sm">
          <span className="font-medium">Your name</span>
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Shown on the version" disabled={saving} />
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium">What changed (optional)</span>
          <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="e.g. New price for the moon charm" disabled={saving} />
        </label>
      </div>
      <ErrorNote error={edit.error} />
      {job?.status === "failed" && <p className="text-sm text-destructive">Saving failed: {job.error}</p>}
      <div className="flex items-center gap-2">
        <Button onClick={save} disabled={!changed || !name.trim() || saving}>
          {saving ? <Loader2 className="animate-spin" /> : <Pencil />}
          {saving ? "Saving and indexing…" : `Save as v${doc.version_count + 1}`}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        {!changed && current.data && <span className="text-xs text-muted-foreground">Change the text to save a new version.</span>}
        {changed && !name.trim() && <span className="text-xs text-muted-foreground">Add your name to save.</span>}
      </div>
    </div>
  );
}
