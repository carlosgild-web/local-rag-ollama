import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";
import { api } from "@/api/client";
import type { EvalCompareSide, EvalMetrics, EvalResult, EvalRun, EvalRunIn, RetrievalMode } from "@/api/types";
import { EmptyState, ErrorNote, JobStatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  useCancelJob,
  useEvalCompare,
  useEvalMutation,
  useEvalRun,
  useProfiles,
} from "@/hooks/queries";
import { cn, formatDate } from "@/lib/utils";
import {
  ChangeBadge,
  formatDelta,
  formatMetric,
  METRICS,
  MODE_LABEL,
  PassBadge,
  rankText,
} from "./format";

// --- Start a run ----------------------------------------------------------------

export function RunForm({ setId, busy }: { setId: number; busy: boolean }) {
  const profiles = useProfiles();
  const [profileId, setProfileId] = useState<string>("");
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [topK, setTopK] = useState("");
  const [answers, setAnswers] = useState(false);
  const [judge, setJudge] = useState(false);
  const [repair, setRepair] = useState(true);
  const [glossary, setGlossary] = useState(true);
  const [label, setLabel] = useState("");
  const start = useEvalMutation((body: EvalRunIn) => api.startEvalRun(body));

  const submit = () =>
    start.mutate({
      eval_set_id: setId,
      profile_id: profileId ? Number(profileId) : undefined,
      mode,
      top_k: topK ? Number(topK) : undefined,
      answers: answers || judge,
      judge,
      repair_citations: repair,
      glossary,
      label: label.trim() || undefined,
    });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Start a run</CardTitle>
        <CardDescription>
          Retrieval only takes seconds. With answers, each question takes about a minute on a CPU, and other jobs
          (uploads too) wait until the run ends.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1">
            <span className="block text-xs text-muted-foreground">Profile</span>
            <select
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              className="h-9 rounded-md border bg-background px-2"
            >
              <option value="">Active default</option>
              {(profiles.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} v{p.version} · {p.chat_model}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="block text-xs text-muted-foreground">Retrieval</span>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as RetrievalMode)}
              className="h-9 rounded-md border bg-background px-2"
            >
              {Object.entries(MODE_LABEL).map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="block text-xs text-muted-foreground">Passages to the model</span>
            <Input
              type="number"
              min={1}
              max={20}
              placeholder="profile's"
              value={topK}
              onChange={(e) => setTopK(e.target.value)}
              className="w-28"
            />
          </label>
          <label className="min-w-48 flex-1 space-y-1">
            <span className="block text-xs text-muted-foreground">Name (optional)</span>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. before the glossary" />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={answers || judge} onChange={(e) => setAnswers(e.target.checked)} />
            Generate answers
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={judge} onChange={(e) => setJudge(e.target.checked)} />
            Judge faithfulness (the chat model checks each answer; twice as slow)
          </label>
          <label className="flex items-center gap-2" title="As the chat does. Turn off to measure the model's own citations.">
            <input type="checkbox" checked={repair} onChange={(e) => setRepair(e.target.checked)} />
            Check citation numbers
          </label>
          <label className="flex items-center gap-2" title="As the chat does. Turn off to measure without it.">
            <input type="checkbox" checked={glossary} onChange={(e) => setGlossary(e.target.checked)} />
            Use the glossary
          </label>
          <Button className="ml-auto" onClick={submit} disabled={busy || start.isPending}>
            {busy ? "A run is going" : "Start run"}
          </Button>
        </div>
        <ErrorNote error={start.error} />
      </CardContent>
    </Card>
  );
}

// --- Runs table -------------------------------------------------------------------

export function RunsTable({
  runs,
  openId,
  selected,
  onOpen,
  onToggle,
}: {
  runs: EvalRun[];
  openId: number | null;
  selected: number[];
  onOpen: (id: number) => void;
  onToggle: (id: number) => void;
}) {
  const cancel = useCancelJob();
  const remove = useEvalMutation((id: number) => api.deleteEvalRun(id));
  if (runs.length === 0) return <EmptyState>No runs yet. Start one above.</EmptyState>;
  const withAnswers = runs.some((r) => r.config.answers);
  const columns = METRICS.filter((m) => withAnswers || !m.answers);
  return (
    <div className="space-y-2">
      <ErrorNote error={cancel.error ?? remove.error} />
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium" title="Pick two runs to compare">
                Compare
              </th>
              <th className="px-3 py-2 font-medium">Run</th>
              <th className="px-3 py-2 font-medium">Status</th>
              {columns.map((m) => (
                <th key={m.key} className="whitespace-nowrap px-3 py-2 text-right font-medium" title={m.hint}>
                  {m.label}
                </th>
              ))}
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {runs.map((run) => {
              const active = run.status === "pending" || run.status === "running";
              return (
                <tr
                  key={run.id}
                  className={cn("cursor-pointer hover:bg-muted/40", openId === run.id && "bg-muted/60")}
                  onClick={() => onOpen(run.id)}
                >
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      aria-label={`Compare run ${run.id}`}
                      checked={selected.includes(run.id)}
                      disabled={run.status !== "completed" || (selected.length >= 2 && !selected.includes(run.id))}
                      onChange={() => onToggle(run.id)}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-medium">
                      #{run.id} {run.label}
                    </div>
                    <div className="text-xs text-muted-foreground">{formatDate(run.created_at)}</div>
                  </td>
                  <td className="px-3 py-2">
                    <JobStatusBadge status={run.status} />
                    {active && <Progress value={run.progress} className="mt-1 w-24" />}
                  </td>
                  {columns.map((m) => (
                    <td key={m.key} className="px-3 py-2 text-right tabular-nums">
                      {formatMetric(run.metrics?.[m.key] as number | null | undefined, m.kind)}
                    </td>
                  ))}
                  <td className="whitespace-nowrap px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                    {active && run.job_id !== null ? (
                      <Button variant="outline" size="sm" onClick={() => cancel.mutate(run.job_id as number)}>
                        Cancel
                      </Button>
                    ) : (
                      <Button variant="ghost" size="sm" onClick={() => remove.mutate(run.id)}>
                        Delete
                      </Button>
                    )}
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

// --- One run's results ----------------------------------------------------------------

export function RunDetail({ runId }: { runId: number }) {
  const run = useEvalRun(runId);
  const [failedOnly, setFailedOnly] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  if (run.error) return <ErrorNote error={run.error} />;
  if (!run.data) return null;
  const data = run.data;
  const results = failedOnly ? data.results.filter((r) => r.passed === false) : data.results;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Run #{data.id}: {data.label}
        </CardTitle>
        <CardDescription>
          {MODE_LABEL[data.config.mode]} retrieval, {data.config.top_k} passages to the model, profile{" "}
          {data.profile ?? "?"}
          {data.config.answers ? `, answers by ${data.chat_model}` : ", retrieval only"}
          {data.config.judge && `, judged by ${data.config.judge_model}`}
          {data.config.answers && data.config.repair_citations === false && ", citation numbers as the model wrote them"}
          {data.config.use_glossary === false
            ? ", without the glossary"
            : data.config.glossary?.length
              ? `, glossary of ${data.config.glossary.length} words`
              : ""}
          .{" "}
          {data.index_snapshot.map((s) => `${s.shelf}: ${s.documents} docs, ${s.chunks} passages`).join(" · ")}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ErrorNote error={data.error} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} />
          Failed only
        </label>
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="w-6" />
                <th className="px-3 py-2 font-medium">Question</th>
                <th className="px-3 py-2 font-medium">Shelf</th>
                <th className="px-3 py-2 font-medium" title="Rank of the first passage from an expected file">
                  Right file
                </th>
                <th className="px-3 py-2 font-medium">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {results.map((result) => (
                <Fragment key={result.id}>
                  <tr className="cursor-pointer hover:bg-muted/40" onClick={() => setOpen(open === result.id ? null : result.id)}>
                    <td className="pl-2 text-muted-foreground">
                      {open === result.id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                    </td>
                    <td className="px-3 py-2">
                      {result.question}
                      {result.expect_not_found && (
                        <Badge variant="outline" className="ml-2">
                          should be not found
                        </Badge>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">{result.shelf ?? "all"}</td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                      {result.expected_sources.length ? rankText(result.first_relevant_rank) : "–"}
                    </td>
                    <td className="px-3 py-2">
                      <PassBadge passed={result.passed} error={result.error} />
                    </td>
                  </tr>
                  {open === result.id && (
                    <tr className="bg-muted/20">
                      <td />
                      <td colSpan={4} className="px-3 py-3">
                        <ResultDetail result={result} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function ResultDetail({ result }: { result: EvalResult }) {
  return (
    <div className="grid gap-3 text-sm md:grid-cols-2">
      <div className="space-y-2">
        {result.error && <p className="text-destructive">{result.error}</p>}
        {result.answer !== null && (
          <div>
            <div className="text-xs font-medium uppercase text-muted-foreground">Answer</div>
            <p className="whitespace-pre-wrap">{result.answer}</p>
          </div>
        )}
        {result.missing_facts && result.missing_facts.length > 0 && (
          <p>
            <span className="font-medium">Missing:</span> {result.missing_facts.map((g) => g.join(" / ")).join("; ")}
          </p>
        )}
        {result.cited_sources !== null && (
          <p>
            <span className="font-medium">Cited:</span> {result.cited_sources.join(", ") || "nothing"}
            {result.citation_status && result.citation_status !== "ok" && ` (${result.citation_status})`}
          </p>
        )}
        {result.faithfulness !== null && (
          <p>
            <span className="font-medium">Judge:</span> {formatMetric(result.faithfulness, "num")}
            {result.judge_note && ` — ${result.judge_note}`}
          </p>
        )}
      </div>
      <div className="space-y-1">
        <div className="text-xs font-medium uppercase text-muted-foreground">Expected</div>
        <p>{result.expect_not_found ? "“not found in the documents”" : result.expected_sources.join(", ") || "–"}</p>
        {result.required_facts.length > 0 && (
          <p className="text-muted-foreground">Facts: {result.required_facts.map((g) => g.join(" / ")).join("; ")}</p>
        )}
        <div className="pt-1 text-xs font-medium uppercase text-muted-foreground">Retrieved (top 5)</div>
        <ol className="list-decimal pl-5">
          {result.retrieved.slice(0, 5).map((r) => (
            <li key={r.chunk_id} className={cn(result.expected_sources.includes(r.filename) && "font-medium text-success")}>
              {r.filename} <span className="text-muted-foreground">({r.score.toFixed(3)})</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

// --- Two runs side by side ---------------------------------------------------------------

export function CompareView({ a, b, onClose }: { a: number; b: number; onClose: () => void }) {
  const compare = useEvalCompare(a, b);
  const [changedOnly, setChangedOnly] = useState(true);
  const [open, setOpen] = useState<string | null>(null);
  if (compare.error) return <ErrorNote error={compare.error} />;
  if (!compare.data) return null;
  const { a: runA, b: runB, same_index, cases } = compare.data;
  const rows = changedOnly ? cases.filter((c) => c.change !== "same") : cases;
  const answers = runA.config.answers || runB.config.answers;
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between">
        <div className="space-y-1">
          <CardTitle className="text-base">
            A: #{runA.id} {runA.label} · B: #{runB.id} {runB.label}
          </CardTitle>
          <CardDescription>
            {same_index
              ? "Both runs searched the same documents and versions."
              : "The documents or their versions changed between the runs, so part of the difference can come from the index."}
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={onClose}>
          Close
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <table className="text-sm">
          <thead className="text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="py-1 pr-6 font-medium" />
              <th className="px-3 py-1 text-right font-medium">A</th>
              <th className="px-3 py-1 text-right font-medium">B</th>
              <th className="px-3 py-1 text-right font-medium">Change</th>
            </tr>
          </thead>
          <tbody>
            {METRICS.filter((m) => answers || !m.answers).map((m) => {
              const va = metric(runA.metrics, m.key);
              const vb = metric(runB.metrics, m.key);
              const delta = formatDelta(va, vb, m.kind);
              return (
                <tr key={m.key}>
                  <td className="py-1 pr-6" title={m.hint}>
                    {m.label}
                  </td>
                  <td className="px-3 py-1 text-right tabular-nums">{formatMetric(va, m.kind)}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{formatMetric(vb, m.kind)}</td>
                  <td className={cn("px-3 py-1 text-right tabular-nums", delta?.tone)}>{delta?.text ?? "–"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={changedOnly} onChange={(e) => setChangedOnly(e.target.checked)} />
          Changed cases only ({cases.filter((c) => c.change !== "same").length} of {cases.length})
        </label>
        {rows.length === 0 ? (
          <EmptyState>No case changed.</EmptyState>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="w-6" />
                  <th className="px-3 py-2 font-medium">Question</th>
                  <th className="px-3 py-2 font-medium">A</th>
                  <th className="px-3 py-2 font-medium">B</th>
                  <th className="px-3 py-2 font-medium">Change</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((row) => {
                  const key = `${row.case_id ?? row.question}-${row.shelf}`;
                  return (
                    <Fragment key={key}>
                      <tr className="cursor-pointer hover:bg-muted/40" onClick={() => setOpen(open === key ? null : key)}>
                        <td className="pl-2 text-muted-foreground">
                          {open === key ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                        </td>
                        <td className="px-3 py-2">
                          {row.question} <span className="text-muted-foreground">· {row.shelf ?? "all"}</span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2">
                          <SideSummary side={row.a} />
                        </td>
                        <td className="whitespace-nowrap px-3 py-2">
                          <SideSummary side={row.b} />
                        </td>
                        <td className="px-3 py-2">
                          <ChangeBadge change={row.change} />
                        </td>
                      </tr>
                      {open === key && (
                        <tr className="bg-muted/20">
                          <td />
                          <td colSpan={4} className="grid gap-3 px-3 py-3 md:grid-cols-2">
                            <SideAnswer label="A" side={row.a} />
                            <SideAnswer label="B" side={row.b} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function metric(metrics: EvalMetrics | null, key: keyof EvalMetrics): number | null | undefined {
  return metrics?.[key] as number | null | undefined;
}

function SideSummary({ side }: { side: EvalCompareSide | null }) {
  if (!side) return <span className="text-muted-foreground">–</span>;
  return (
    <span className="inline-flex items-center gap-2">
      <PassBadge passed={side.passed} error={side.error} />
      <span className="tabular-nums text-muted-foreground">{rankText(side.first_relevant_rank)}</span>
    </span>
  );
}

function SideAnswer({ label, side }: { label: string; side: EvalCompareSide | null }) {
  return (
    <div className="space-y-1 text-sm">
      <div className="text-xs font-medium uppercase text-muted-foreground">{label}</div>
      {!side ? (
        <p className="text-muted-foreground">Not in this run.</p>
      ) : (
        <>
          <p>Top file: {side.top_source ?? "nothing retrieved"}</p>
          {side.answer !== null && <p className="whitespace-pre-wrap">{side.answer}</p>}
          {side.missing_facts && side.missing_facts.length > 0 && (
            <p className="text-destructive">Missing: {side.missing_facts.map((g) => g.join(" / ")).join("; ")}</p>
          )}
          {side.cited_sources && <p className="text-muted-foreground">Cited: {side.cited_sources.join(", ") || "nothing"}</p>}
        </>
      )}
    </div>
  );
}
