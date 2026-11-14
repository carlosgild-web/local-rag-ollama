import { History, Plus, RotateCcw, Save, ScanSearch } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Profile, ProfileVersion } from "@/api/types";
import { DiffLines } from "@/components/DiffLines";
import { EmptyState, ErrorNote, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { InfoTip } from "@/components/ui/tooltip";
import {
  useModels,
  useProfileCompare,
  useProfiles,
  useProfileVersions,
  useRestoreProfile,
  useSaveProfile,
} from "@/hooks/queries";
import { cn, formatDate } from "@/lib/utils";

/** The grounding rule every prompt must keep (invariant 6; checked by the server too). */
const NOT_FOUND_PHRASE = "not found in the documents";

const FIELD_LABEL: Record<string, string> = {
  chat_model: "Chat model",
  embedding_model: "Embedding model",
  chunk_size_tokens: "Chunk size",
  chunk_overlap_pct: "Chunk overlap",
  retrieval_top_k: "Passages sent (top-k)",
  temperature: "Temperature",
  system_prompt: "System prompt",
};

interface Draft {
  chat_model: string;
  retrieval_top_k: number;
  temperature: number;
  system_prompt: string;
}

const draftOf = (p: Profile): Draft => ({
  chat_model: p.chat_model,
  retrieval_top_k: p.retrieval_top_k,
  temperature: p.temperature,
  system_prompt: p.system_prompt,
});

export default function Profiles() {
  const profiles = useProfiles();
  const list = profiles.data ?? [];
  const [name, setName] = useState("default");
  const [creating, setCreating] = useState(false);
  const active = list.find((p) => p.name === name) ?? list[0];

  return (
    <>
      <PageHeader
        title="Profiles"
        description="The settings the chat answers with. Every save is a new version, and each answer records the version it used."
        actions={
          <Button variant="outline" size="sm" onClick={() => setCreating(true)} disabled={!active}>
            <Plus /> New profile
          </Button>
        }
      />
      <div className="space-y-6 px-8 py-6">
        <ErrorNote error={profiles.error} />
        {list.length > 1 && (
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Profiles">
            {list.map((p) => (
              <button
                key={p.name}
                type="button"
                role="tab"
                aria-selected={p.name === active?.name}
                onClick={() => setName(p.name)}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-sm",
                  p.name === active?.name ? "border-primary bg-primary/5 font-medium" : "text-muted-foreground hover:bg-accent",
                )}
              >
                {p.name} <span className="text-xs text-muted-foreground">v{p.version}</span>
              </button>
            ))}
          </div>
        )}
        {active && (
          <div className="grid gap-6 xl:grid-cols-[1fr_26rem]">
            <Editor key={active.id} profile={active} />
            <VersionHistory profile={active} />
          </div>
        )}
      </div>
      {active && (
        <NewProfileDialog
          open={creating}
          from={active}
          taken={list.map((p) => p.name)}
          onClose={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false);
            setName(created);
          }}
        />
      )}
    </>
  );
}

function Editor({ profile }: { profile: Profile }) {
  const models = useModels();
  const save = useSaveProfile();
  const [draft, setDraft] = useState<Draft>(() => draftOf(profile));
  const original = useMemo(() => draftOf(profile), [profile]);
  const dirty = (Object.keys(draft) as (keyof Draft)[]).filter((k) => draft[k] !== original[k]);
  const keepsRule = draft.system_prompt.includes(NOT_FOUND_PHRASE);

  const chatModels = (models.data ?? []).filter((m) => !m.capabilities.includes("embedding") || m.capabilities.includes("completion"));
  const installed = chatModels.some((m) => m.name === draft.chat_model);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle>
            {profile.name} <span className="font-normal text-muted-foreground">v{profile.version}</span>
          </CardTitle>
          <CardDescription>Saving creates v{profile.version + 1}. Earlier versions are kept.</CardDescription>
        </div>
        <Button variant="ghost" size="sm" asChild>
          <Link to={`/inspector?profile=${encodeURIComponent(profile.name)}`}>
            <ScanSearch /> Try in the inspector
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span className="font-medium">Chat model</span>
            <select
              className="w-full rounded-md border bg-background px-2 py-1.5"
              value={draft.chat_model}
              onChange={(e) => set("chat_model", e.target.value)}
            >
              {!installed && <option value={draft.chat_model}>{draft.chat_model} (not installed)</option>}
              {chatModels.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                  {m.parameter_size ? ` · ${m.parameter_size}` : ""}
                </option>
              ))}
            </select>
            {!installed && models.isSuccess && (
              <span className="block text-xs text-warning">
                Ollama doesn't have this model. <Link to="/models" className="underline">Pull it</Link> or pick another.
              </span>
            )}
          </label>
          <NumberField
            label="Passages sent (top-k)"
            tip="How many of the best passages go into the prompt. More gives the model more to read, and makes answers slower."
            value={draft.retrieval_top_k}
            min={1}
            max={50}
            step={1}
            onChange={(v) => set("retrieval_top_k", v)}
          />
          <NumberField
            label="Temperature"
            tip="0 gives the same answer every time (decision 0016). Higher values vary the wording, and make made-up details more likely."
            value={draft.temperature}
            min={0}
            max={2}
            step={0.1}
            onChange={(v) => set("temperature", v)}
          />
        </div>

        <label className="block space-y-1 text-sm">
          <span className="flex items-center gap-1.5 font-medium">
            System prompt
            <InfoTip label="About the system prompt">
              The instructions before the passages. They must keep the rule to answer "{NOT_FOUND_PHRASE}" when the passages don't
              answer the question.
            </InfoTip>
          </span>
          <Textarea
            className="min-h-64 font-mono text-xs leading-relaxed"
            value={draft.system_prompt}
            onChange={(e) => set("system_prompt", e.target.value)}
          />
          {!keepsRule && (
            <span className="block text-xs text-destructive">
              The prompt must still tell the model to say "{NOT_FOUND_PHRASE}" when the answer isn't in the passages.
            </span>
          )}
        </label>

        <div className="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          Recorded with the profile, but each shelf has its own: embedding model {profile.embedding_model}, chunks of{" "}
          {profile.chunk_size_tokens} tokens with {Math.round(profile.chunk_overlap_pct * 100)}% overlap. Change them per shelf in{" "}
          <Link to="/collections" className="underline">
            Collections
          </Link>
          .
        </div>

        <ErrorNote error={save.error} />
        <div className="flex items-center justify-end gap-2">
          {dirty.length > 0 && (
            <span className="mr-auto text-xs text-muted-foreground">Changed: {dirty.map((k) => FIELD_LABEL[k]).join(", ")}</span>
          )}
          <Button variant="ghost" onClick={() => setDraft(original)} disabled={dirty.length === 0 || save.isPending}>
            Discard
          </Button>
          <Button
            disabled={dirty.length === 0 || !keepsRule || save.isPending}
            onClick={() =>
              save.mutate({ name: profile.name, ...Object.fromEntries(dirty.map((k) => [k, draft[k]])) })
            }
          >
            <Save /> {save.isPending ? "Saving…" : `Save as v${profile.version + 1}`}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function NumberField({
  label,
  tip,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  tip: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="space-y-1 text-sm">
      <span className="flex items-center gap-1.5 font-medium">
        {label}
        <InfoTip label={`About ${label}`}>{tip}</InfoTip>
      </span>
      <Input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (!Number.isNaN(v)) onChange(Math.min(max, Math.max(min, v)));
        }}
      />
    </label>
  );
}

function VersionHistory({ profile }: { profile: Profile }) {
  const versions = useProfileVersions(profile.id);
  const list = versions.data ?? [];
  const [pair, setPair] = useState<{ a: number; b: number } | null>(null);
  const [restoring, setRestoring] = useState<ProfileVersion | null>(null);

  // Default comparison: the active version against the one before it.
  useEffect(() => {
    if (list.length >= 2 && (pair === null || !list.some((v) => v.id === pair.a) || !list.some((v) => v.id === pair.b)))
      setPair({ a: list[1].id, b: list[0].id });
  }, [list, pair]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="size-4" /> Versions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          <ErrorNote error={versions.error} />
          {list.map((v) => (
            <div key={v.id} className={cn("flex items-center gap-3 rounded-md px-2 py-2 text-sm", v.is_active && "bg-primary/5")}>
              <span className="w-8 font-medium">v{v.version}</span>
              <span className="flex-1 text-xs text-muted-foreground">
                {formatDate(v.created_at)}
                <span className="block">
                  {v.answer_count} answer{v.answer_count === 1 ? "" : "s"}
                  {v.eval_run_count > 0 && ` · ${v.eval_run_count} evaluation run${v.eval_run_count === 1 ? "" : "s"}`}
                </span>
              </span>
              {v.is_active ? (
                <Badge variant="success">active</Badge>
              ) : (
                <>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPair({ a: v.id, b: list[0].id })}
                    title={`Compare v${v.version} with the active version`}
                  >
                    Compare
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setRestoring(v)}>
                    <RotateCcw /> Restore
                  </Button>
                </>
              )}
            </div>
          ))}
          {list.length === 1 && <p className="px-2 text-xs text-muted-foreground">Only one version so far.</p>}
        </CardContent>
      </Card>
      {pair && list.length >= 2 && <Compare versions={list} pair={pair} onPair={setPair} />}
      <RestoreDialog key={restoring?.id ?? "none"} version={restoring} activeVersion={profile.version} onClose={() => setRestoring(null)} />
    </div>
  );
}

function Compare({
  versions,
  pair,
  onPair,
}: {
  versions: ProfileVersion[];
  pair: { a: number; b: number };
  onPair: (pair: { a: number; b: number }) => void;
}) {
  const compare = useProfileCompare(pair.a, pair.b);
  const data = compare.data;
  const pick = (key: "a" | "b") => (
    <select
      className="rounded-md border bg-background px-2 py-1 text-sm"
      value={pair[key]}
      onChange={(e) => onPair({ ...pair, [key]: Number(e.target.value) })}
      aria-label={key === "a" ? "Older version" : "Newer version"}
    >
      {versions.map((v) => (
        <option key={v.id} value={v.id}>
          v{v.version}
        </option>
      ))}
    </select>
  );
  const fields = data?.changes.filter((c) => c.field !== "system_prompt") ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          Compare {pick("a")} with {pick("b")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorNote error={compare.error} />
        {data && data.changes.length === 0 && <EmptyState>These two versions have the same settings.</EmptyState>}
        {fields.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1">Setting</th>
                <th className="py-1">v{data?.a.version}</th>
                <th className="py-1">v{data?.b.version}</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((c) => (
                <tr key={c.field} className="border-t">
                  <td className="py-1.5">{FIELD_LABEL[c.field] ?? c.field}</td>
                  <td className="py-1.5 text-destructive line-through decoration-red-300">{String(c.a)}</td>
                  <td className="py-1.5 font-medium text-success">{String(c.b)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data && data.prompt_diff.length > 0 && (
          <div className="space-y-1">
            <p className="text-sm font-medium">System prompt</p>
            <DiffLines diff={data.prompt_diff} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RestoreDialog({
  version,
  activeVersion,
  onClose,
}: {
  version: ProfileVersion | null;
  activeVersion: number;
  onClose: () => void;
}) {
  const restore = useRestoreProfile();
  if (!version) return null;
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Restore v${version.version}?`}
      description={`Its settings are saved as v${activeVersion + 1}, which the chat then uses. v${activeVersion} and every other version are kept.`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={restore.isPending} onClick={() => restore.mutate(version.id, { onSuccess: onClose })}>
            <RotateCcw /> {restore.isPending ? "Restoring…" : `Restore as v${activeVersion + 1}`}
          </Button>
        </>
      }
    >
      <ErrorNote error={restore.error} />
      <p className="text-sm text-muted-foreground">The restore is recorded in the audit log.</p>
    </Dialog>
  );
}

function NewProfileDialog({
  open,
  from,
  taken,
  onClose,
  onCreated,
}: {
  open: boolean;
  from: Profile;
  taken: string[];
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const save = useSaveProfile();
  const [name, setName] = useState("");
  const clean = name.trim();
  const clash = taken.includes(clean);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New profile"
      description={`Starts as a copy of ${from.name} v${from.version}. The chat keeps using "default"; other profiles are for the inspector and evaluation runs.`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!clean || clash || save.isPending}
            onClick={() =>
              save.mutate(
                { name: clean, ...draftOf(from) },
                {
                  onSuccess: () => {
                    setName("");
                    onCreated(clean);
                  },
                },
              )
            }
          >
            Create
          </Button>
        </>
      }
    >
      <label className="block space-y-1 text-sm">
        <span className="font-medium">Name</span>
        <Input value={name} maxLength={64} onChange={(e) => setName(e.target.value)} placeholder="e.g. short-answers" />
        {clash && <span className="text-xs text-destructive">A profile with this name already exists.</span>}
      </label>
      <div className="mt-3">
        <ErrorNote error={save.error} />
      </div>
    </Dialog>
  );
}
