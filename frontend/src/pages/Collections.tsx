import { AlertTriangle, ExternalLink, HelpCircle, Plus, RefreshCw, Shuffle, XCircle } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";
import type { Collection, CollectionReindex, Model } from "@/api/types";
import { ErrorNote, PageHeader } from "@/components/common";
import { GlossaryCard } from "@/components/GlossaryCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { InfoTip } from "@/components/ui/tooltip";
import {
  useCollections,
  useCreateCollection,
  useModels,
  useReindexCollection,
  useSetPortalVisible,
} from "@/hooks/queries";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { type Advice, adviseSettings, PRESETS } from "@/lib/chunking";
import { cn, formatDate } from "@/lib/utils";

/** A step that waits for "Yes" in a confirmation dialog. */
interface Pending {
  title: string;
  body: ReactNode;
  warnings: Advice[];
  confirmLabel: string;
  run: () => void;
}

export default function Collections() {
  const [showInactive, setShowInactive] = useState(false);
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const collections = useCollections(showInactive);
  const reindex = useReindexCollection();
  const system = useSystemStatus();
  const processBlocked = system.processBlocked;

  return (
    <>
      <PageHeader
        title="Collections"
        description="Separate shelves for your documents. Chat answers from one shelf; Luna, in the employee portal, searches every shelf shared with it."
        actions={
          <Button
            onClick={() => setCreating((v) => !v)}
            disabled={!!processBlocked}
            title={processBlocked ? `Paused: ${processBlocked}` : undefined}
          >
            <Plus /> New collection
          </Button>
        }
      />
      <div className="space-y-4 px-8 py-6">
        {processBlocked && (
          <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
            Creating, reindexing and rebuilding shelves is paused because {processBlocked}. You can still look
            around.
          </p>
        )}
        <CollectionsHelp />
        {creating && <CreateForm onDone={() => setCreating(false)} ask={setPending} />}

        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          Show old copies kept after a rebuild
        </label>

        <ErrorNote error={collections.error ?? reindex.error} />
        {reindex.data && (
          <p className="text-sm text-muted-foreground">
            {reindex.data.mode === "blue_green"
              ? `Rebuilding into a new generation (collection #${reindex.data.target_collection_id}). The current one keeps answering until the swap.`
              : "Reindex queued."}{" "}
            Follow it in the <Link to="/queue" className="underline">queue</Link>.
          </p>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          {collections.data?.map((c) => (
            <CollectionCard
              key={c.id}
              collection={c}
              onReindex={(body) => reindex.mutate({ id: c.id, body })}
              ask={setPending}
              blocked={processBlocked}
            />
          ))}
        </div>
        <GlossaryCard />
      </div>
      {pending && <ConfirmDialog pending={pending} onClose={() => setPending(null)} />}
    </>
  );
}

function ConfirmDialog({ pending, onClose }: { pending: Pending; onClose: () => void }) {
  return (
    <Dialog
      open
      onClose={onClose}
      className="max-w-lg"
      title={pending.title}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              pending.run();
              onClose();
            }}
          >
            {pending.confirmLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        {pending.body}
        {pending.warnings.length > 0 && (
          <div className="space-y-1 rounded-md border border-warning/40 bg-warning/10 px-3 py-2">
            <p className="font-medium">Unusual settings: are you sure?</p>
            {pending.warnings.map((w) => (
              <p key={w.text}>{w.text}</p>
            ))}
          </div>
        )}
      </div>
    </Dialog>
  );
}

const pieces = (body: CollectionReindex, fallback?: Collection) => {
  const model = body.embedding_model ?? fallback?.embedding_model ?? "the default embedding model";
  const size = body.chunk_size_tokens ?? fallback?.chunk_size_tokens;
  const overlap = body.chunk_overlap_pct ?? fallback?.chunk_overlap_pct;
  return (
    <>
      <strong>{model}</strong>
      {size !== undefined && (
        <>
          , in pieces of <strong>{size} tokens</strong>
        </>
      )}
      {overlap !== undefined && (
        <>
          {" "}
          with <strong>{Math.round(overlap * 100)}% overlap</strong>
        </>
      )}
    </>
  );
};

function CollectionCard({
  collection: c,
  onReindex,
  ask,
  blocked,
}: {
  collection: Collection;
  onReindex: (body?: CollectionReindex) => void;
  ask: (pending: Pending) => void;
  blocked: string | null;
}) {
  const [editing, setEditing] = useState(false);
  const docs = `${c.document_count} document${c.document_count === 1 ? "" : "s"}`;
  return (
    <Card className={c.is_active ? "" : "opacity-60"}>
      <CardHeader className="flex-row items-start justify-between">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2">
            {c.name}
            {c.is_active ? <Badge variant="success">active</Badge> : <Badge variant="outline">retired</Badge>}
          </CardTitle>
          <CardDescription>Created {formatDate(c.created_at)}</CardDescription>
        </div>
        {c.is_active && !blocked && (
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="sm"
              title="Read every document on this shelf again"
              onClick={() =>
                ask({
                  title: `Reindex "${c.name}"?`,
                  body: (
                    <p>
                      Reads the {docs} on this shelf again with the same settings. Useful after an update, or if
                      answers miss something that is clearly in a document. It runs in the background.
                    </p>
                  ),
                  warnings: [],
                  confirmLabel: "Reindex",
                  run: () => onReindex(),
                })
              }
            >
              <RefreshCw /> Reindex
            </Button>
            <Button
              variant="ghost"
              size="sm"
              title="Advanced: change how this shelf reads its documents"
              onClick={() => setEditing((v) => !v)}
            >
              <Shuffle /> Change
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
          <dt className="text-muted-foreground">Documents</dt>
          <dd>{c.document_count}</dd>
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            Embedding model <InfoTip label="What is the embedding model?">{TIPS.model}</InfoTip>
          </dt>
          <dd className="font-mono text-xs">{c.embedding_model}</dd>
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            Chunk size <InfoTip label="What is the chunk size?">{TIPS.size}</InfoTip>
          </dt>
          <dd>{c.chunk_size_tokens} tokens</dd>
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            Overlap <InfoTip label="What is the overlap?">{TIPS.overlap}</InfoTip>
          </dt>
          <dd>{Math.round(c.chunk_overlap_pct * 100)}%</dd>
        </dl>
        {c.is_active && <PortalSwitch collection={c} />}
        {editing && (
          <SettingsForm
            initial={c}
            submitLabel="Rebuild with these settings…"
            onSubmit={(body, warnings) => {
              const same =
                (body.embedding_model ?? c.embedding_model) === c.embedding_model &&
                (body.chunk_size_tokens ?? c.chunk_size_tokens) === c.chunk_size_tokens &&
                Math.round((body.chunk_overlap_pct ?? c.chunk_overlap_pct) * 100) ===
                  Math.round(c.chunk_overlap_pct * 100);
              ask({
                title: same ? `Nothing changed: reindex "${c.name}"?` : `Rebuild "${c.name}"?`,
                body: same ? (
                  <p>These are the shelf's current settings, so this only reads the {docs} again.</p>
                ) : (
                  <>
                    <p>
                      Re-reads the {docs} with {pieces(body, c)}.
                    </p>
                    <p className="text-muted-foreground">
                      A new copy of the shelf is built in the background. The current copy keeps answering until it
                      is ready, then they swap; the old copy is kept (see "Show old copies").
                    </p>
                  </>
                ),
                warnings,
                confirmLabel: same ? "Reindex" : "Rebuild",
                run: () => {
                  onReindex(body);
                  setEditing(false);
                },
              });
            }}
          />
        )}
      </CardContent>
    </Card>
  );
}

/** Whether Luna, the employee portal assistant, searches this shelf. */
function PortalSwitch({ collection: c }: { collection: Collection }) {
  const setVisible = useSetPortalVisible();
  const id = `portal-visible-${c.id}`;
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border bg-muted/30 px-3 py-2.5">
      <div className="text-sm">
        <label htmlFor={id} className="font-medium">
          Visible in the employee portal
        </label>
        <p className="text-xs text-muted-foreground">
          {c.portal_visible
            ? "Luna, the portal assistant, searches this shelf."
            : "Hidden: Luna never answers from this shelf."}{" "}
          <a href="/intranet" target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 underline">
            Open the portal <ExternalLink className="size-3" />
          </a>
        </p>
        <ErrorNote error={setVisible.error} />
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={c.portal_visible}
        disabled={setVisible.isPending}
        onClick={() => setVisible.mutate({ id: c.id, visible: !c.portal_visible })}
        className={cn(
          "relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-60",
          c.portal_visible ? "bg-primary" : "bg-muted-foreground/40",
        )}
      >
        <span
          className={cn(
            "inline-block size-4 rounded-full bg-white shadow transition-transform",
            c.portal_visible ? "translate-x-4.5" : "translate-x-0.5",
          )}
        />
      </button>
    </div>
  );
}

const SHELF_NAME = /^[A-Za-z0-9_-]{1,64}$/;

function CreateForm({ onDone, ask }: { onDone: () => void; ask: (pending: Pending) => void }) {
  const [name, setName] = useState("");
  const create = useCreateCollection();
  const trimmed = name.trim();
  const badName = trimmed !== "" && !SHELF_NAME.test(trimmed);
  return (
    <Card>
      <CardHeader>
        <CardTitle>New collection</CardTitle>
        <CardDescription>
          Pick a name. The reading settings start at the recommended values; most shelves never need others.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <Input
            placeholder="Name (letters, digits, - and _)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={cn("max-w-sm", badName && "border-destructive")}
          />
          {badName && (
            <p className="text-xs text-destructive">Use only letters, digits, - and _ (no spaces), up to 64 characters.</p>
          )}
        </div>
        <SettingsForm
          defaults
          submitLabel="Create…"
          disabled={!trimmed || badName || create.isPending}
          onSubmit={(body, warnings) =>
            ask({
              title: `Create the shelf "${trimmed}"?`,
              body: (
                <>
                  <p>Documents on it will be read with {pieces(body)}.</p>
                  <p className="text-muted-foreground">
                    You can change this later, but that rebuilds the shelf (every document is read again).
                  </p>
                </>
              ),
              warnings,
              confirmLabel: "Create",
              run: () => create.mutate({ name: trimmed, ...body }, { onSuccess: onDone }),
            })
          }
        />
        <ErrorNote error={create.error} />
      </CardContent>
    </Card>
  );
}

const TIPS = {
  model: (
    <>
      The model that turns each piece of text into numbers, so the app can find the pieces closest to your question.
      Every document on a shelf uses the same one. Changing it rebuilds the shelf: every document is read again,
      and the current copy keeps answering until the new one is ready.
    </>
  ),
  size: (
    <>
      Documents are cut into pieces, and a question is answered from the few best pieces. Small pieces find exact facts
      but lose the context around them; large pieces keep context but are less precise. 600 tokens (about 450 words)
      suits most documents. Changing it rebuilds the shelf.
    </>
  ),
  overlap: (
    <>
      How much of each piece is repeated at the start of the next one, so a sentence cut at a boundary is still seen
      whole. 10–15% is plenty. Changing it rebuilds the shelf.
    </>
  ),
};

function SettingsForm({
  initial,
  defaults,
  submitLabel,
  disabled,
  onSubmit,
}: {
  initial?: Collection;
  /** Start from the recommended preset (new shelves). */
  defaults?: boolean;
  submitLabel: string;
  disabled?: boolean;
  onSubmit: (body: CollectionReindex, warnings: Advice[]) => void;
}) {
  const models = useModels();
  const balanced = PRESETS[1];
  const [model, setModel] = useState(initial?.embedding_model ?? "");
  const [size, setSize] = useState(
    initial ? String(initial.chunk_size_tokens) : defaults ? String(balanced.size) : "",
  );
  const [overlap, setOverlap] = useState(
    initial ? String(Math.round(initial.chunk_overlap_pct * 100)) : defaults ? String(balanced.overlapPct) : "",
  );

  const options = embeddingModelOptions(models.data ?? [], model);
  const advice = adviseSettings(size, overlap, model, models.data ?? []);
  const errors = advice.filter((a) => a.level === "error");
  const warnings = advice.filter((a) => a.level === "warning");
  const flagged = (field: Advice["field"]) => {
    const a = advice.find((x) => x.field === field);
    return a ? (a.level === "error" ? "border-destructive" : "border-warning") : "";
  };

  const submit = () => {
    const body: CollectionReindex = {};
    if (model) body.embedding_model = model;
    if (size) body.chunk_size_tokens = Number(size);
    if (overlap) body.chunk_overlap_pct = Number(overlap) / 100;
    onSubmit(body, warnings);
  };

  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Presets:</span>
        {PRESETS.map((p) => {
          const active = size === String(p.size) && overlap === String(p.overlapPct);
          return (
            <Button
              key={p.id}
              type="button"
              variant={active ? "default" : "outline"}
              size="sm"
              title={`${p.size} tokens, ${p.overlapPct}% overlap`}
              onClick={() => {
                setSize(String(p.size));
                setOverlap(String(p.overlapPct));
              }}
            >
              {p.label}
              <span className={cn("text-xs", active ? "opacity-80" : "text-muted-foreground")}>· {p.hint}</span>
            </Button>
          );
        })}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            Embedding model <InfoTip label="What is the embedding model?">{TIPS.model}</InfoTip>
          </span>
          <select
            className={cn("block h-9 rounded-md border border-input bg-background px-2", flagged("model"))}
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            <option value="">Default</option>
            {options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            Chunk size (tokens) <InfoTip label="What is the chunk size?">{TIPS.size}</InfoTip>
          </span>
          <Input
            type="number"
            min={50}
            max={4000}
            value={size}
            onChange={(e) => setSize(e.target.value)}
            className={cn("w-32", flagged("size"))}
          />
        </label>
        <label className="space-y-1">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            Overlap (%) <InfoTip label="What is the overlap?">{TIPS.overlap}</InfoTip>
          </span>
          <Input
            type="number"
            min={0}
            max={49}
            value={overlap}
            onChange={(e) => setOverlap(e.target.value)}
            className={cn("w-24", flagged("overlap"))}
          />
        </label>
        <Button onClick={submit} disabled={disabled || errors.length > 0}>
          {submitLabel}
        </Button>
      </div>
      {advice.length > 0 && (
        <ul className="space-y-1">
          {advice.map((a) => (
            <li
              key={a.text}
              className={cn("flex items-start gap-2 text-xs", a.level === "error" ? "text-destructive" : "text-warning")}
            >
              {a.level === "error" ? (
                <XCircle className="mt-0.5 size-3.5 shrink-0" />
              ) : (
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              )}
              <span>
                {a.text}
                {a.field !== "model" && " A preset above fills in values that work."}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const HELP_KEY = "help.collections.open";

/** Plain-language explanation; open until the user folds it away. */
function CollectionsHelp() {
  const [open, setOpen] = useState(() => localStorage.getItem(HELP_KEY) !== "false");
  return (
    <details
      open={open}
      onToggle={(e) => {
        const next = e.currentTarget.open;
        setOpen(next);
        localStorage.setItem(HELP_KEY, String(next));
      }}
      className="rounded-lg border bg-accent/40 px-5 py-3 text-sm"
    >
      <summary className="flex cursor-pointer items-center gap-2 font-medium text-accent-foreground">
        <HelpCircle className="size-4" /> How collections work
      </summary>
      <div className="mt-3 space-y-3 text-foreground/90">
        <p>
          A collection is a <strong>separate shelf</strong> for your documents. When you ask a
          question, the app reads only the documents on <strong>one shelf</strong>, so answers stay
          on topic. For example: an <em>HR</em> shelf for holidays and policies, a{" "}
          <em>Products</em> shelf for catalogs and price lists.
        </p>
        <p>
          If all your documents are about one subject, the <strong>default</strong> shelf is all you
          need. When you add files, the Library suggests a shelf for each one (or a new shelf), and
          the Chat asks which shelf to search.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <strong>A document lives on one shelf.</strong> Uploading a file that is already on
            another shelf is skipped, not copied.
          </li>
          <li>
            <strong>Reindex</strong> reads every document on the shelf again. Rarely needed: after
            an update, or if answers miss something that is clearly in a document.
          </li>
          <li>
            <strong>Change</strong> is an advanced setting for how documents are read. The shelf is
            rebuilt in the background and the old copy keeps answering until the new one is ready.
          </li>
        </ul>
      </div>
    </details>
  );
}

const baseName = (name: string) => name.replace(/:latest$/, "");

/** Embedding models only (a chat model here would break the shelf), each
 * listed once: "bge-m3" and "bge-m3:latest" are the same model. The current
 * value keeps its exact spelling so the select shows it. */
export function embeddingModelOptions(models: Model[], current: string): string[] {
  const knowsCapabilities = models.some((m) => m.capabilities.length > 0);
  const names = models
    .filter((m) => !knowsCapabilities || m.capabilities.includes("embedding"))
    .map((m) => (current && baseName(m.name) === baseName(current) ? current : m.name));
  if (current && !names.includes(current)) names.push(current);
  return [...new Set(names)];
}
