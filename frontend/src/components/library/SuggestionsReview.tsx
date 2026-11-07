import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FolderPlus, Library, Loader2, Play, Plus, Sparkles, X } from "lucide-react";
import { type ReactNode, useState } from "react";
import { api } from "@/api/client";
import type { Collection, Intake, IntakeFile, IntakeStatus } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, formatBytes } from "@/lib/utils";

const STATUS: Record<IntakeStatus, { label: string; variant: "success" | "default" | "secondary" | "warning" | "destructive" }> = {
  new: { label: "New", variant: "success" },
  new_version: { label: "New version", variant: "default" },
  name_in_trash: { label: "Name in trash", variant: "warning" },
  duplicate: { label: "Already in library", variant: "secondary" },
  unsupported: { label: "Can't be read", variant: "destructive" },
  unreadable: { label: "Can't be read", variant: "destructive" },
  empty: { label: "Empty", variant: "destructive" },
  too_large: { label: "Too large", variant: "destructive" },
  pending: { label: "Not analyzed", variant: "secondary" },
};

// Same rule as the server (app/ingest/intake.py SHELF_NAME).
const SHELF_NAME = /^[a-z0-9][a-z0-9_-]{0,47}$/;

interface Decision {
  include: boolean;
  shelf: string;
  tags: string[];
}

interface NewShelf {
  name: string;
  description: string;
  namedBy: string;
}

/** The app's suggestions for one batch: files grouped by suggested shelf,
 * each shelf, file and tag changeable, then one confirmation. */
export function SuggestionsReview({
  batch,
  existing,
  onConfirmed,
  onCancel,
}: {
  batch: Intake;
  /** All active shelves, including ones the batch didn't suggest. */
  existing: Collection[];
  onConfirmed: (jobIds: number[]) => void;
  onCancel: () => void;
}) {
  const client = useQueryClient();
  const [decisions, setDecisions] = useState<Record<string, Decision>>(() =>
    Object.fromEntries(
      batch.files.map((f) => [f.key, { include: f.include && !!f.shelf, shelf: f.shelf ?? "", tags: f.tags }]),
    ),
  );
  const [newShelves, setNewShelves] = useState<Record<string, NewShelf>>(() =>
    Object.fromEntries(
      batch.shelves
        .filter((s) => !s.existing)
        .map((s) => [s.ref, { name: s.name, description: s.description, namedBy: s.named_by }]),
    ),
  );
  const [busy, setBusy] = useState<"confirm" | "cancel" | null>(null);
  const [error, setError] = useState<unknown>(null);

  // The picked folder's own name starts every path: show what is below it.
  const firstParts = new Set(batch.files.map((f) => (f.path.includes("/") ? f.path.split("/")[0] : "")));
  const root = firstParts.size === 1 ? [...firstParts][0] : "";
  const shown = (path: string) => (root ? path.slice(root.length + 1) : path);
  const offered = batch.files.filter((f) => f.include && f.shelf);
  const leftOut = batch.files.filter((f) => !(f.include && f.shelf));
  const shelfName = (ref: string) =>
    newShelves[ref]?.name ?? existing.find((c) => `existing:${c.id}` === ref)?.name ?? ref;

  // Groups in a stable order: suggested new shelves first, then existing ones.
  const groups = (() => {
    const refs = [
      ...Object.keys(newShelves),
      ...existing.map((c) => `existing:${c.id}`),
    ].filter((ref) => offered.some((f) => decisions[f.key].shelf === ref));
    return refs.map((ref) => ({ ref, files: offered.filter((f) => decisions[f.key].shelf === ref) }));
  })();

  const chosen = offered.filter((f) => decisions[f.key].include);
  const usedNew = [...new Set(chosen.map((f) => decisions[f.key].shelf))].filter((ref) => ref in newShelves);
  const nameProblem = (ref: string): string | null => {
    const name = newShelves[ref].name.trim().toLowerCase();
    if (!SHELF_NAME.test(name)) return "Use lowercase letters, digits, - and _ (no spaces), up to 48 characters.";
    if (existing.some((c) => c.name === name)) return `A shelf called "${name}" already exists: pick it from the list instead.`;
    if (usedNew.some((other) => other !== ref && newShelves[other].name.trim().toLowerCase() === name))
      return "Two new shelves have this name.";
    return null;
  };
  const invalid = usedNew.some((ref) => nameProblem(ref) !== null);

  const update = (key: string, change: Partial<Decision>) =>
    setDecisions((d) => ({ ...d, [key]: { ...d[key], ...change } }));

  const addShelf = (): string => {
    let n = 1;
    while (`new:u${n}` in newShelves) n += 1;
    const taken = new Set([...existing.map((c) => c.name), ...Object.values(newShelves).map((s) => s.name)]);
    let name = "new-shelf";
    for (let i = 2; taken.has(name); i += 1) name = `new-shelf-${i}`;
    const ref = `new:u${n}`;
    setNewShelves((s) => ({ ...s, [ref]: { name, description: "", namedBy: "user" } }));
    return ref;
  };
  const moveTo = (keys: string[], value: string) => {
    const ref = value === "__new__" ? addShelf() : value;
    setDecisions((d) => {
      const next = { ...d };
      for (const key of keys) next[key] = { ...next[key], shelf: ref };
      return next;
    });
  };

  const confirm = async () => {
    setBusy("confirm");
    setError(null);
    try {
      const result = await api.confirmIntake(batch.batch_id, {
        new_shelves: Object.fromEntries(usedNew.map((ref) => [ref, newShelves[ref].name.trim().toLowerCase()])),
        files: offered.map((f) => ({ key: f.key, ...decisions[f.key] })),
      });
      client.invalidateQueries({ queryKey: ["collections"] });
      client.invalidateQueries({ queryKey: ["jobs"] });
      onConfirmed(result.job_ids);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const cancel = async () => {
    setBusy("cancel");
    try {
      await api.cancelIntake(batch.batch_id);
    } catch {
      // already gone (expired): nothing to clean up
    }
    setBusy(null);
    onCancel();
  };

  const shelfOptions = (
    <>
      {Object.entries(newShelves).map(([ref, s]) => (
        <option key={ref} value={ref}>
          {s.name} (new)
        </option>
      ))}
      {existing.map((c) => (
        <option key={c.id} value={`existing:${c.id}`}>
          {c.name}
        </option>
      ))}
      <option value="__new__">New shelf…</option>
    </>
  );

  return (
    <div className="space-y-4 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-start gap-3">
        <Sparkles className="mt-0.5 size-5 text-primary" />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold">Suggested shelves and tags</h3>
          <p className="text-sm text-muted-foreground">
            The app read {batch.files.length} file{batch.files.length === 1 ? "" : "s"}
            {root && ` from the folder "${root}"`} and suggests where each one belongs.
            Change any shelf, name or tag, then confirm. Nothing is in the library until you do.
          </p>
        </div>
      </div>

      {groups.map(({ ref, files }) => {
        const isNew = ref in newShelves;
        const shelf = newShelves[ref];
        const problem = isNew && files.some((f) => decisions[f.key].include) ? nameProblem(ref) : null;
        return (
          <section key={ref} className="overflow-hidden rounded-lg border">
            <header className="flex flex-wrap items-center gap-3 border-b bg-muted/50 px-4 py-3 text-sm">
              {isNew ? <FolderPlus className="size-4 text-primary" /> : <Library className="size-4 text-muted-foreground" />}
              {isNew ? (
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">New shelf{shelf.namedBy === "user" ? "" : " (suggested)"}:</span>
                    <Input
                      aria-label="New shelf name"
                      value={shelf.name}
                      onChange={(e) => setNewShelves((s) => ({ ...s, [ref]: { ...s[ref], name: e.target.value } }))}
                      className={cn("h-8 w-56 font-mono", problem && "border-destructive")}
                    />
                    {shelf.namedBy === "keywords" && (
                      <span className="text-xs text-muted-foreground">named from keywords (the model didn't answer)</span>
                    )}
                  </div>
                  {shelf.description && <p className="text-xs text-muted-foreground">{shelf.description}</p>}
                  {problem && <p className="text-xs text-destructive">{problem}</p>}
                </div>
              ) : (
                <span className="flex-1">
                  Shelf <span className="font-medium">{shelfName(ref)}</span>
                  <span className="text-muted-foreground"> · already in the library</span>
                </span>
              )}
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                Move all to
                <select
                  className="h-8 rounded-md border border-input bg-background px-2 text-foreground"
                  value=""
                  onChange={(e) => e.target.value && moveTo(files.map((f) => f.key), e.target.value)}
                >
                  <option value="">—</option>
                  {shelfOptions}
                </select>
              </label>
            </header>
            <ul className="divide-y">
              {files.map((file) => (
                <FileRow
                  key={file.key}
                  file={file}
                  label={shown(file.path)}
                  decision={decisions[file.key]}
                  alternativeNames={file.alternatives.map(shelfName)}
                  shelfOptions={shelfOptions}
                  onChange={(change) => update(file.key, change)}
                  onMove={(value) => moveTo([file.key], value)}
                />
              ))}
            </ul>
          </section>
        );
      })}

      {leftOut.length > 0 && (
        <section className="overflow-hidden rounded-lg border">
          <header className="border-b bg-muted/50 px-4 py-2 text-sm font-medium">
            Left out ({leftOut.length}): nothing to do for these
          </header>
          <ul className="divide-y text-sm">
            {leftOut.map((file) => (
              <li key={file.key} className="flex flex-wrap items-center gap-2 px-4 py-2 opacity-80">
                <span className="break-all font-medium">{shown(file.path)}</span>
                <Badge variant={STATUS[file.status].variant}>{STATUS[file.status].label}</Badge>
                <span className="w-full text-muted-foreground">{file.message}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <ErrorNote error={error} />
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" onClick={cancel} disabled={!!busy}>
          {busy === "cancel" ? <Loader2 className="animate-spin" /> : <X />} Cancel
        </Button>
        <span className="ml-auto text-sm text-muted-foreground">
          {chosen.length} of {batch.files.length} will be processed
        </span>
        {offered.length === 0 ? (
          <Button onClick={cancel} disabled={!!busy}>
            Nothing to process: close
          </Button>
        ) : (
          <Button onClick={confirm} disabled={chosen.length === 0 || invalid || !!busy}>
            {busy === "confirm" ? <Loader2 className="animate-spin" /> : <Play />}
            {usedNew.length > 0
              ? `Create ${usedNew.length} ${usedNew.length === 1 ? "shelf" : "shelves"} and process ${chosen.length} document${chosen.length === 1 ? "" : "s"}`
              : `Process ${chosen.length} document${chosen.length === 1 ? "" : "s"}`}
          </Button>
        )}
      </div>
    </div>
  );
}

function FileRow({
  file,
  label,
  decision,
  alternativeNames,
  shelfOptions,
  onChange,
  onMove,
}: {
  file: IntakeFile;
  label: string;
  decision: Decision;
  alternativeNames: string[];
  shelfOptions: ReactNode;
  onChange: (change: Partial<Decision>) => void;
  onMove: (value: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const status = STATUS[file.status];
  const addTag = () => {
    const tag = draft.trim().replace(/,/g, "");
    if (tag && !decision.tags.some((t) => t.toLowerCase() === tag.toLowerCase())) onChange({ tags: [...decision.tags, tag] });
    setDraft("");
  };
  return (
    <li className={cn("space-y-2 px-4 py-3 text-sm", !decision.include && "opacity-60")}>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="checkbox"
          aria-label={`Process ${file.path}`}
          checked={decision.include}
          onChange={(e) => onChange({ include: e.target.checked })}
        />
        <span className="break-all font-medium">{label}</span>
        <span className="text-xs text-muted-foreground">{formatBytes(file.size)}</span>
        <Badge variant={status.variant}>{status.label}</Badge>
        {file.confidence === "low" && (
          <Badge variant="warning">
            <AlertTriangle className="size-3" /> Please check
          </Badge>
        )}
        <label className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
          Shelf
          <select
            aria-label={`Shelf for ${file.path}`}
            className="h-8 rounded-md border border-input bg-background px-2 text-foreground"
            value={decision.shelf}
            onChange={(e) => onMove(e.target.value)}
          >
            {shelfOptions}
          </select>
        </label>
      </div>
      <p className="text-xs text-muted-foreground">
        {file.reason}
        {file.status !== "new" && file.message && ` · ${file.message}`}
        {alternativeNames.length > 0 && file.confidence === "low" && ` (alternative: ${alternativeNames.join(", ")})`}
      </p>
      <div className="flex flex-wrap items-center gap-1.5">
        {decision.tags.map((tag) => (
          <span
            key={tag}
            className={cn(
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs",
              file.tags.includes(tag) ? "bg-secondary" : "border",
            )}
            title={file.tags.includes(tag) ? "Suggested tag" : "Added by you"}
          >
            {file.tags.includes(tag) && <Sparkles className="size-3 text-primary" />}
            {tag}
            <button
              type="button"
              aria-label={`Remove tag ${tag}`}
              className="text-muted-foreground hover:text-foreground"
              onClick={() => onChange({ tags: decision.tags.filter((t) => t !== tag) })}
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <form
          className="inline-flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            addTag();
          }}
        >
          <Input
            aria-label={`Add a tag to ${file.path}`}
            placeholder="add tag"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="h-7 w-24 px-2 text-xs"
          />
          <Button type="submit" variant="ghost" size="sm" className="h-7 px-1.5" disabled={!draft.trim()} aria-label="Add tag">
            <Plus />
          </Button>
        </form>
      </div>
    </li>
  );
}
