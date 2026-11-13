import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import type { EvalCase, EvalCaseIn } from "@/api/types";
import { EmptyState, ErrorNote, PageHeader } from "@/components/common";
import { CaseEditor } from "@/components/eval/CaseEditor";
import { CompareView, RunDetail, RunForm, RunsTable } from "@/components/eval/RunViews";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { useEvalDemo, useEvalMutation, useEvalRuns, useEvalSet, useEvalSets } from "@/hooks/queries";
import { cn } from "@/lib/utils";

type Tab = "runs" | "questions";

/** Golden sets, runs and comparisons (Phase 7, decision 0019). The chosen set,
 * tab, open run and compared runs live in the URL, so a view can be linked. */
export default function Evaluation() {
  const [params, setParams] = useSearchParams();
  const sets = useEvalSets();
  const demo = useEvalDemo();
  const setParam = (changes: Record<string, string | null>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(changes)) {
          if (value === null) next.delete(key);
          else next.set(key, value);
        }
        return next;
      },
      { replace: true },
    );

  const setId = Number(params.get("set")) || sets.data?.[0]?.id || null;
  const tab: Tab = params.get("tab") === "questions" ? "questions" : "runs";
  const current = sets.data?.find((s) => s.id === setId) ?? null;

  const loadDemo = useEvalMutation(() => api.loadEvalDemo());
  const removeSet = useEvalMutation((id: number) => api.deleteEvalSet(id));
  const importSet = useEvalMutation((body: unknown) => api.importEvalSet(body));
  const [creating, setCreating] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const onImport = async (file: File | undefined) => {
    if (!file) return;
    try {
      const created = await importSet.mutateAsync(JSON.parse(await file.text()));
      setParam({ set: String(created.id), run: null, a: null, b: null });
    } catch {
      // shown by ErrorNote (a bad JSON file shows the parser's message)
    }
  };

  const demoButton = demo.data?.available && demo.data.loaded_set_id === null && (
    <Button
      variant="outline"
      disabled={loadDemo.isPending}
      onClick={() => loadDemo.mutate(undefined, { onSuccess: (s) => setParam({ set: String(s.id) }) })}
    >
      Load the demo golden set
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Evaluation"
        description="Ask a golden set of questions with known answers, score retrieval and answers, and compare runs."
        actions={
          <>
            {sets.data && sets.data.length > 0 && (
              <select
                aria-label="Golden set"
                value={setId ?? ""}
                onChange={(e) => setParam({ set: e.target.value, run: null, a: null, b: null })}
                className="h-9 rounded-md border bg-background px-2 text-sm"
              >
                {sets.data.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.case_count})
                  </option>
                ))}
              </select>
            )}
            {demoButton}
            <Button variant="outline" onClick={() => setCreating(true)}>
              New set
            </Button>
            <Button variant="outline" onClick={() => fileInput.current?.click()}>
              Import
            </Button>
            <input
              ref={fileInput}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(e) => {
                onImport(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </>
        }
      />
      <div className="space-y-6 px-8 py-6">
        <ErrorNote error={sets.error ?? loadDemo.error ?? importSet.error ?? removeSet.error} />
        {sets.isSuccess && sets.data.length === 0 ? (
          <EmptyState>
            <p>No golden sets yet.</p>
            <p className="mt-1">
              {demo.data?.available
                ? "The demo company's set has 53 questions on its four shelves, ready to run once the demo documents are loaded."
                : "Create one and add questions with the files and facts a good answer needs."}
            </p>
          </EmptyState>
        ) : (
          current && (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex rounded-md border p-0.5 text-sm">
                  {(["runs", "questions"] as Tab[]).map((value) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setParam({ tab: value === "runs" ? null : value })}
                      className={cn("rounded px-3 py-1", tab === value ? "bg-muted font-medium" : "text-muted-foreground")}
                    >
                      {value === "runs" ? `Runs (${current.run_count})` : `Questions (${current.case_count})`}
                    </button>
                  ))}
                </div>
                {current.description && <p className="text-sm text-muted-foreground">{current.description}</p>}
                <div className="ml-auto flex gap-2">
                  <Button variant="ghost" size="sm" asChild>
                    <a href={api.evalSetExportUrl(current.id)}>Export JSON</a>
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (window.confirm(`Delete the golden set "${current.name}" with its questions and runs?`)) {
                        removeSet.mutate(current.id, { onSuccess: () => setParam({ set: null, run: null }) });
                      }
                    }}
                  >
                    Delete set
                  </Button>
                </div>
              </div>
              {tab === "runs" ? (
                <RunsTab setId={current.id} params={params} setParam={setParam} />
              ) : (
                <QuestionsTab setId={current.id} />
              )}
            </>
          )
        )}
      </div>
      {creating && <NewSetDialog onClose={() => setCreating(false)} onCreated={(id) => setParam({ set: String(id) })} />}
    </>
  );
}

function RunsTab({
  setId,
  params,
  setParam,
}: {
  setId: number;
  params: URLSearchParams;
  setParam: (changes: Record<string, string | null>) => void;
}) {
  const runs = useEvalRuns(setId);
  const [selected, setSelected] = useState<number[]>([]);
  const openId = Number(params.get("run")) || null;
  const a = Number(params.get("a")) || null;
  const b = Number(params.get("b")) || null;
  const busy = runs.data?.some((r) => r.status === "pending" || r.status === "running") ?? false;
  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div className="space-y-4">
      <RunForm setId={setId} busy={busy} />
      <ErrorNote error={runs.error} />
      {runs.data && (
        <>
          <div className="flex items-center gap-3">
            <h2 className="font-semibold">Runs</h2>
            <Button
              size="sm"
              variant="outline"
              disabled={selected.length !== 2}
              onClick={() => {
                // Older run on the left: "A → B" reads as before → after.
                const [first, second] = [...selected].sort((x, y) => x - y);
                setParam({ a: String(first), b: String(second), run: null });
              }}
            >
              Compare {selected.length === 2 ? "the two picked runs" : "(pick two)"}
            </Button>
          </div>
          <RunsTable
            runs={runs.data}
            openId={openId}
            selected={selected}
            onOpen={(id) => setParam({ run: openId === id ? null : String(id), a: null, b: null })}
            onToggle={toggle}
          />
        </>
      )}
      {a !== null && b !== null ? (
        <CompareView a={a} b={b} onClose={() => setParam({ a: null, b: null })} />
      ) : (
        openId !== null && <RunDetail runId={openId} />
      )}
    </div>
  );
}

function QuestionsTab({ setId }: { setId: number }) {
  const detail = useEvalSet(setId);
  const [editing, setEditing] = useState<EvalCase | "new" | null>(null);
  const add = useEvalMutation((body: EvalCaseIn) => api.addEvalCase(setId, body));
  const update = useEvalMutation(({ id, body }: { id: number; body: EvalCaseIn }) => api.updateEvalCase(id, body));
  const remove = useEvalMutation((id: number) => api.deleteEvalCase(id));
  const saving = add.isPending || update.isPending;
  const close = () => {
    setEditing(null);
    add.reset();
    update.reset();
  };
  const save = (body: EvalCaseIn) => {
    if (editing === "new") add.mutate(body, { onSuccess: close });
    else if (editing) update.mutate({ id: editing.id, body }, { onSuccess: close });
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <p className="text-sm text-muted-foreground">
          Editing a question doesn't change runs already made: each run keeps its own copy.
        </p>
        <Button size="sm" className="ml-auto" onClick={() => setEditing("new")}>
          Add question
        </Button>
      </div>
      <ErrorNote error={detail.error ?? remove.error} />
      {detail.data && detail.data.cases.length === 0 && <EmptyState>No questions yet.</EmptyState>}
      {detail.data && detail.data.cases.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Question</th>
                <th className="px-3 py-2 font-medium">Shelf</th>
                <th className="px-3 py-2 font-medium">Expected</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {detail.data.cases.map((c) => (
                <tr key={c.id}>
                  <td className="px-3 py-2">
                    {c.question}
                    <div className="mt-0.5 flex flex-wrap gap-1">
                      {c.kind && <Badge variant="secondary">{c.kind}</Badge>}
                      {c.variant_group && <Badge variant="outline">wording: {c.variant_group}</Badge>}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">{c.shelf ?? "all shelves"}</td>
                  <td className="px-3 py-2">
                    {c.expect_not_found ? (
                      <span className="text-muted-foreground">“not found”</span>
                    ) : (
                      <>
                        <div>{c.expected_sources.join(", ") || "–"}</div>
                        {c.required_facts.length > 0 && (
                          <div className="text-xs text-muted-foreground">
                            {c.required_facts.map((g) => g.join(" / ")).join("; ")}
                          </div>
                        )}
                      </>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    <Button variant="ghost" size="sm" onClick={() => setEditing(c)}>
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => window.confirm("Delete this question?") && remove.mutate(c.id)}
                    >
                      Delete
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing !== null && (
        <CaseEditor
          open
          initial={editing === "new" ? null : editing}
          saving={saving}
          error={add.error ?? update.error}
          onSave={save}
          onClose={close}
        />
      )}
    </div>
  );
}

function NewSetDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const create = useEvalMutation((body: { name: string; description: string }) => api.createEvalSet(body));
  return (
    <Dialog
      open
      onClose={onClose}
      title="New golden set"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!name.trim() || create.isPending}
            onClick={() =>
              create.mutate(
                { name: name.trim(), description },
                {
                  onSuccess: (s) => {
                    onCreated(s.id);
                    onClose();
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
      <div className="space-y-3 text-sm">
        <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        <Textarea
          placeholder="What it covers (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
        />
        <ErrorNote error={create.error} />
      </div>
    </Dialog>
  );
}
