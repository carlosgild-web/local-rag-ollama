import { CheckCircle2, Download, Loader2, MessageSquare, Trash2, X } from "lucide-react";
import { useState } from "react";
import type { Model } from "@/api/types";
import { EmptyState, ErrorNote, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useDeleteModel, useModels, useProfiles, useSaveProfile } from "@/hooks/queries";
import { usePullModel } from "@/hooks/usePullModel";
import { formatBytes, formatDate } from "@/lib/utils";

/** Models this app is tested with (PLAN.md section 2, decision 0004). Sizes are Ollama's downloads, roughly. */
const SUGGESTED = [
  { name: "qwen2.5:3b", hint: "chat · about 1.9 GB · runs on 8 GB of RAM" },
  { name: "llama3.2:3b", hint: "chat · about 2.0 GB" },
  { name: "qwen2.5:7b", hint: "chat · about 4.7 GB · 16 GB of RAM" },
  { name: "llama3.1:8b", hint: "chat · about 4.9 GB · 16 GB of RAM" },
  { name: "bge-m3", hint: "embeddings · about 1.2 GB · Spanish and English" },
];

const sameModel = (name: string) => name.trim().toLowerCase().replace(/:latest$/, "");
const isEmbedding = (m: Model) => m.capabilities.includes("embedding") && !m.capabilities.includes("completion");

export default function Models() {
  const models = useModels();
  const profiles = useProfiles();
  const defaultProfile = profiles.data?.find((p) => p.name === "default");
  const [deleting, setDeleting] = useState<Model | null>(null);
  const [chatting, setChatting] = useState<Model | null>(null);
  const list = models.data ?? [];
  const installed = new Set(list.map((m) => sameModel(m.name)));

  return (
    <>
      <PageHeader
        title="Models"
        description="The models Ollama has on this machine. Pull new ones, choose the chat model, and delete the ones nothing uses."
      />
      <div className="space-y-6 px-8 py-6">
        <PullCard installed={installed} />
        <ErrorNote error={models.error} />
        {models.isSuccess && list.length === 0 && <EmptyState>Ollama has no models yet. Pull one above.</EmptyState>}
        {list.length > 0 && (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2">Model</th>
                  <th className="px-4 py-2">Kind</th>
                  <th className="px-4 py-2">Size</th>
                  <th className="px-4 py-2">Used by</th>
                  <th className="px-4 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.map((m) => {
                  const isChat = defaultProfile && sameModel(defaultProfile.chat_model) === sameModel(m.name);
                  return (
                    <tr key={m.name} className="border-t align-top">
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{m.name}</span>
                          {isChat && <Badge variant="default">chat model</Badge>}
                          {m.loaded && (
                            <Badge variant="success" title="Ollama holds it in memory, so the next answer starts faster">
                              in memory
                            </Badge>
                          )}
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {[m.family, m.parameter_size].filter(Boolean).join(" · ")}
                          {m.modified_at && ` · pulled ${formatDate(m.modified_at)}`}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs">{isEmbedding(m) ? "Embeddings" : m.capabilities.length ? "Chat" : "—"}</td>
                      <td className="px-4 py-3 tabular-nums">{formatBytes(m.size)}</td>
                      <td className="px-4 py-3 text-xs">
                        {m.used_by.length === 0 ? (
                          <span className="text-muted-foreground">Nothing</span>
                        ) : (
                          <ul className="space-y-0.5">
                            {m.used_by.map((u) => (
                              <li key={u}>{u}</li>
                            ))}
                          </ul>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-2">
                          {!isEmbedding(m) && !isChat && defaultProfile && (
                            <Button variant="outline" size="sm" onClick={() => setChatting(m)}>
                              <MessageSquare /> Use for chat
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setDeleting(m)}
                            disabled={m.used_by.length > 0}
                            title={m.used_by.length > 0 ? `In use: ${m.used_by.join("; ")}` : `Delete ${m.name}`}
                            aria-label={`Delete ${m.name}`}
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
      <DeleteDialog key={`d-${deleting?.name}`} model={deleting} onClose={() => setDeleting(null)} />
      {defaultProfile && (
        <UseForChatDialog
          key={`c-${chatting?.name}`}
          model={chatting}
          current={defaultProfile.chat_model}
          version={defaultProfile.version}
          onClose={() => setChatting(null)}
        />
      )}
    </>
  );
}

function PullCard({ installed }: { installed: Set<string> }) {
  const { state, pull, cancel, clear } = usePullModel();
  const [name, setName] = useState("");
  const running = state?.phase === "running";
  const share = state?.total ? (state.completed ?? 0) / state.total : 0;
  const start = (model: string) => {
    if (!model.trim()) return;
    setName(model);
    void pull(model.trim());
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pull a model</CardTitle>
        <CardDescription>
          Downloads from the Ollama library, like <code>ollama pull</code>. Nothing is downloaded unless you ask.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            start(name);
          }}
        >
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. qwen2.5:7b" disabled={running} />
          <Button type="submit" disabled={!name.trim() || running}>
            <Download /> Pull
          </Button>
        </form>
        <div className="flex flex-wrap gap-2">
          {SUGGESTED.map((s) => {
            const have = installed.has(sameModel(s.name));
            return (
              <button
                key={s.name}
                type="button"
                disabled={running || have}
                onClick={() => start(s.name)}
                className="rounded-md border px-2.5 py-1 text-left text-xs hover:bg-accent disabled:cursor-default disabled:opacity-60 disabled:hover:bg-transparent"
                title={have ? "Already pulled" : `Pull ${s.name}`}
              >
                <span className="font-medium">{s.name}</span>
                {have && <CheckCircle2 className="ml-1 inline size-3 text-success" />}
                <span className="block text-muted-foreground">{s.hint}</span>
              </button>
            );
          })}
        </div>

        {state && (
          <div className="space-y-1.5 rounded-md border bg-muted/30 px-3 py-2">
            <div className="flex items-center gap-2 text-sm">
              {running && <Loader2 className="size-4 animate-spin" />}
              {state.phase === "done" && <CheckCircle2 className="size-4 text-success" />}
              <span className="font-medium">{state.name}</span>
              <span className="text-muted-foreground">
                {state.phase === "done"
                  ? "pulled"
                  : state.phase === "cancelled"
                    ? "cancelled"
                    : state.phase === "error"
                      ? "failed"
                      : state.status}
              </span>
              <span className="ml-auto flex items-center gap-1">
                {running ? (
                  <Button variant="ghost" size="sm" onClick={cancel}>
                    Cancel
                  </Button>
                ) : (
                  <button type="button" onClick={clear} aria-label="Dismiss" className="rounded p-1 text-muted-foreground hover:bg-muted">
                    <X className="size-3.5" />
                  </button>
                )}
              </span>
            </div>
            {running && state.total ? (
              <>
                <Progress value={share} />
                <p className="text-xs tabular-nums text-muted-foreground">
                  {formatBytes(state.completed)} of {formatBytes(state.total)} ({Math.round(share * 100)}%)
                </p>
              </>
            ) : null}
            {state.phase === "error" && <ErrorNote error={state.error} />}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DeleteDialog({ model, onClose }: { model: Model | null; onClose: () => void }) {
  const remove = useDeleteModel();
  if (!model) return null;
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Delete ${model.name}?`}
      description={`Ollama removes it from this machine and frees ${formatBytes(model.size)}. Nothing in the app uses it; you can pull it again later.`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate(model.name, { onSuccess: onClose })}>
            <Trash2 /> {remove.isPending ? "Deleting…" : "Delete"}
          </Button>
        </>
      }
    >
      <ErrorNote error={remove.error} />
      <p className="text-sm text-muted-foreground">The delete is recorded in the audit log.</p>
    </Dialog>
  );
}

function UseForChatDialog({
  model,
  current,
  version,
  onClose,
}: {
  model: Model | null;
  current: string;
  version: number;
  onClose: () => void;
}) {
  const save = useSaveProfile();
  if (!model) return null;
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Chat with ${model.name}?`}
      description={`Saves profile default v${version + 1} with ${model.name} instead of ${current}. Every other setting stays; v${version} is kept and can be restored on the Profiles page.`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={save.isPending}
            onClick={() => save.mutate({ name: "default", chat_model: model.name }, { onSuccess: onClose })}
          >
            <MessageSquare /> {save.isPending ? "Saving…" : `Use ${model.name}`}
          </Button>
        </>
      }
    >
      <ErrorNote error={save.error} />
      <p className="text-sm text-muted-foreground">
        A bigger model usually answers better and needs more memory. Measure the change on the Evaluation page before
        keeping it.
      </p>
    </Dialog>
  );
}
