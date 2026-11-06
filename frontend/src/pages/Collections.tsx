import { HelpCircle, Plus, RefreshCw, Shuffle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Collection, CollectionReindex, Model } from "@/api/types";
import { ErrorNote, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCollections, useCreateCollection, useModels, useReindexCollection } from "@/hooks/queries";
import { formatDate } from "@/lib/utils";

export default function Collections() {
  const [showInactive, setShowInactive] = useState(false);
  const [creating, setCreating] = useState(false);
  const collections = useCollections(showInactive);
  const reindex = useReindexCollection();

  return (
    <>
      <PageHeader
        title="Collections"
        description="Separate shelves for your documents. A question is answered from one shelf only."
        actions={
          <Button onClick={() => setCreating((v) => !v)}>
            <Plus /> New collection
          </Button>
        }
      />
      <div className="space-y-4 px-8 py-6">
        <CollectionsHelp />
        {creating && <CreateForm onDone={() => setCreating(false)} />}

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
            />
          ))}
        </div>
      </div>
    </>
  );
}

function CollectionCard({
  collection: c,
  onReindex,
}: {
  collection: Collection;
  onReindex: (body?: CollectionReindex) => void;
}) {
  const [editing, setEditing] = useState(false);
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
        {c.is_active && (
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" title="Read every document on this shelf again" onClick={() => onReindex()}>
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
          <dt className="text-muted-foreground">Embedding model</dt>
          <dd className="font-mono text-xs">{c.embedding_model}</dd>
          <dt className="text-muted-foreground">Chunk size</dt>
          <dd>{c.chunk_size_tokens} tokens</dd>
          <dt className="text-muted-foreground">Overlap</dt>
          <dd>{Math.round(c.chunk_overlap_pct * 100)}%</dd>
        </dl>
        {editing && (
          <SettingsForm
            initial={c}
            submitLabel="Rebuild with these settings"
            onSubmit={(body) => {
              onReindex(body);
              setEditing(false);
            }}
          />
        )}
      </CardContent>
    </Card>
  );
}

function CreateForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const create = useCreateCollection();
  return (
    <Card>
      <CardHeader>
        <CardTitle>New collection</CardTitle>
        <CardDescription>Leave settings empty to use the defaults from the server.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input
          placeholder="Name (letters, digits, - and _)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="max-w-sm"
        />
        <SettingsForm
          submitLabel="Create"
          disabled={!name.trim() || create.isPending}
          onSubmit={(body) => create.mutate({ name: name.trim(), ...body }, { onSuccess: onDone })}
        />
        <ErrorNote error={create.error} />
      </CardContent>
    </Card>
  );
}

function SettingsForm({
  initial,
  submitLabel,
  disabled,
  onSubmit,
}: {
  initial?: Collection;
  submitLabel: string;
  disabled?: boolean;
  onSubmit: (body: CollectionReindex) => void;
}) {
  const models = useModels();
  const [model, setModel] = useState(initial?.embedding_model ?? "");
  const [size, setSize] = useState(initial ? String(initial.chunk_size_tokens) : "");
  const [overlap, setOverlap] = useState(initial ? String(Math.round(initial.chunk_overlap_pct * 100)) : "");

  const options = embeddingModelOptions(models.data ?? [], model);

  const submit = () => {
    const body: CollectionReindex = {};
    if (model) body.embedding_model = model;
    if (size) body.chunk_size_tokens = Number(size);
    if (overlap) body.chunk_overlap_pct = Number(overlap) / 100;
    onSubmit(body);
  };

  return (
    <div className="flex flex-wrap items-end gap-3 text-sm">
      <label className="space-y-1">
        <span className="text-xs text-muted-foreground">Embedding model</span>
        <select
          className="block h-9 rounded-md border border-input bg-background px-2"
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
        <span className="text-xs text-muted-foreground">Chunk size (tokens)</span>
        <Input type="number" min={50} max={4000} value={size} onChange={(e) => setSize(e.target.value)} className="w-32" />
      </label>
      <label className="space-y-1">
        <span className="text-xs text-muted-foreground">Overlap (%)</span>
        <Input type="number" min={0} max={49} value={overlap} onChange={(e) => setOverlap(e.target.value)} className="w-24" />
      </label>
      <Button onClick={submit} disabled={disabled}>
        {submitLabel}
      </Button>
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
          need. Once you have a second shelf, the Library asks where to put new files and the Chat
          asks which shelf to search.
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
