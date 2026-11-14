import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Copy, RotateCcw, Search } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { InspectChunk, InspectIn, InspectOut, RetrievalMode } from "@/api/types";
import { EmptyState, ErrorNote, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { InfoTip } from "@/components/ui/tooltip";
import { useCollections, useInspect, useProfiles } from "@/hooks/queries";
import { useDebounced } from "@/hooks/useDebounced";
import { cn } from "@/lib/utils";

/** Same heuristic as the chunker (decision 0001). */
const CHARS_PER_TOKEN = 4;

const MODES: { id: RetrievalMode; label: string; hint: string }[] = [
  { id: "hybrid", label: "Hybrid", hint: "Vectors and keywords, fused (the chat)" },
  { id: "vector", label: "Vector", hint: "Meaning only" },
  { id: "keyword", label: "Keyword", hint: "Exact words only (BM25)" },
];

/** Overrides of the chat's settings; null = what the chat uses. */
interface Overrides {
  mode: RetrievalMode;
  topK: number | null;
  candidates: number | null;
  vectorWeight: number;
  minCosine: number;
  rerank: boolean | null;
}

const CHAT_DEFAULTS: Overrides = {
  mode: "hybrid",
  topK: null,
  candidates: null,
  vectorWeight: 0.5,
  minCosine: 0,
  rerank: null,
};

export default function Inspector() {
  const collections = useCollections();
  const profiles = useProfiles();
  const shelves = collections.data ?? [];

  const [draft, setDraft] = useState("");
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState<string>(""); // "all" | "portal" | shelf id
  const [searchParams] = useSearchParams();
  // The Profiles page links here with ?profile=<name>.
  const [profile, setProfile] = useState(searchParams.get("profile") || "default");
  const [overrides, setOverrides] = useState<Overrides>(CHAT_DEFAULTS);

  useEffect(() => {
    if (scope === "" && shelves.length > 0) setScope(String(shelves[0].id));
  }, [scope, shelves]);

  const body: InspectIn | null = useMemo(() => {
    if (!question || !scope) return null;
    return {
      question,
      scope: scope === "all" || scope === "portal" ? scope : "shelf",
      collection_id: scope === "all" || scope === "portal" ? undefined : Number(scope),
      profile,
      mode: overrides.mode,
      top_k: overrides.topK ?? undefined,
      candidates: overrides.candidates ?? undefined,
      vector_weight: overrides.vectorWeight,
      min_cosine: overrides.minCosine,
      rerank: overrides.rerank ?? undefined,
    };
  }, [question, scope, profile, overrides]);

  // Sliders re-query after a short pause; the reranker toggle is slow anyway.
  const inspect = useInspect(useDebounced(body, 300));
  const data = inspect.data;
  const params = data?.parameters;
  const moved = useRankChanges(data, question);

  const set = <K extends keyof Overrides>(key: K, value: Overrides[K]) =>
    setOverrides((o) => ({ ...o, [key]: value }));
  const changed = (Object.keys(CHAT_DEFAULTS) as (keyof Overrides)[]).filter(
    (k) => overrides[k] !== CHAT_DEFAULTS[k],
  );

  return (
    <>
      <PageHeader
        title="Retrieval inspector"
        description="See which passages a question finds, why they rank where they do, and the exact prompt the model gets. Nothing here changes the chat."
      />
      <div className="grid gap-6 px-8 py-6 lg:grid-cols-[20rem_1fr]">
        <div className="space-y-4">
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              setQuestion(draft.trim());
            }}
          >
            <label className="text-sm font-medium" htmlFor="inspect-question">
              Question
            </label>
            <div className="flex gap-2">
              <Input
                id="inspect-question"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="How many PTO days do I get?"
              />
              <Button type="submit" size="icon" aria-label="Inspect" disabled={!draft.trim()}>
                <Search className="size-4" />
              </Button>
            </div>
          </form>

          <div className="grid grid-cols-2 gap-2">
            <Picker label="Shelf" value={scope} onChange={setScope}>
              {shelves.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
              {shelves.length > 1 && <option value="all">All shelves</option>}
              <option value="portal">Portal shelves</option>
            </Picker>
            <Picker label="Profile" value={profile} onChange={setProfile}>
              {(profiles.data ?? [{ name: "default", version: 1 }]).map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} v{p.version}
                </option>
              ))}
            </Picker>
          </div>

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm">Retrieval settings</CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setOverrides(CHAT_DEFAULTS)}
                disabled={changed.length === 0}
                title="Back to what the chat uses"
              >
                <RotateCcw className="size-3.5" /> Chat settings
              </Button>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-1.5">
                <span className="text-sm font-medium">Search</span>
                <div className="grid grid-cols-3 gap-1 rounded-md bg-muted p-1" role="radiogroup" aria-label="Search mode">
                  {MODES.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      role="radio"
                      aria-checked={overrides.mode === m.id}
                      title={m.hint}
                      onClick={() => set("mode", m.id)}
                      className={cn(
                        "rounded px-2 py-1 text-xs font-medium text-muted-foreground transition-colors",
                        overrides.mode === m.id && "bg-background text-foreground shadow-sm",
                      )}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>

              <Slider
                label="Passages sent (top-k)"
                tip="How many of the best passages go into the prompt. The chat uses the profile's value."
                min={1}
                max={20}
                step={1}
                value={overrides.topK ?? params?.top_k ?? 5}
                isDefault={overrides.topK === null}
                onChange={(v) => set("topK", v)}
                format={(v) => String(v)}
              />
              <Slider
                label="Candidates per side"
                tip="How many passages vector search and keyword search each find before they are fused. Also how many the reranker rescores."
                min={1}
                max={50}
                step={1}
                value={overrides.candidates ?? params?.candidates ?? 20}
                isDefault={overrides.candidates === null}
                onChange={(v) => set("candidates", v)}
                format={(v) => String(v)}
              />
              <Slider
                label="Vector weight"
                tip="How much meaning counts against exact words when the two lists are fused (weighted RRF). 0.5 weighs them equally, like the chat."
                min={0}
                max={1}
                step={0.05}
                value={overrides.vectorWeight}
                isDefault={overrides.vectorWeight === 0.5}
                disabled={overrides.mode !== "hybrid"}
                onChange={(v) => set("vectorWeight", v)}
                format={(v) => (v === 0.5 ? "0.50 (equal)" : v.toFixed(2))}
              />
              <Slider
                label="Cosine floor"
                tip="Vector matches less similar than this are dropped. 0 = off, like the chat. Keyword matches are never dropped."
                min={0}
                max={0.9}
                step={0.01}
                value={overrides.minCosine}
                isDefault={overrides.minCosine === 0}
                disabled={overrides.mode === "keyword"}
                onChange={(v) => set("minCosine", v)}
                format={(v) => (v === 0 ? "off" : v.toFixed(2))}
              />

              <label
                className={cn("flex items-start gap-2 text-sm", data && !data.reranker_available && "opacity-60")}
                title={data && !data.reranker_available ? "Download the model first: python -m app.cli reranker-download" : undefined}
              >
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={overrides.rerank ?? params?.rerank ?? false}
                  disabled={!data?.reranker_available}
                  onChange={(e) => set("rerank", e.target.checked)}
                />
                <span>
                  <span className="font-medium">Reranker</span>
                  <span className="block text-xs text-muted-foreground">
                    bge-reranker-v2-m3 rescores the candidates. Adds several seconds on a CPU.
                  </span>
                </span>
              </label>
            </CardContent>
          </Card>
          {changed.length > 0 && (
            <p className="text-xs text-warning">
              Different from the chat: {changed.map((k) => LABELS[k]).join(", ")}. The chat's answers still use its own settings.
            </p>
          )}
        </div>

        <div className="min-w-0 space-y-4">
          {collections.isSuccess && shelves.length === 0 ? (
            <EmptyState>
              No shelves yet. <Link to="/library" className="underline">Upload documents</Link> first.
            </EmptyState>
          ) : !question ? (
            <EmptyState>Ask a question to see what retrieval finds. Then move the sliders and watch the ranking change.</EmptyState>
          ) : (
            <>
              <ErrorNote error={inspect.error} />
              {data && <Summary data={data} loading={inspect.isFetching} />}
              {data && data.chunks.length === 0 && (
                <EmptyState>Nothing found. The chat would answer that it's not in the documents.</EmptyState>
              )}
              {data && data.chunks.length > 0 && <Results data={data} moved={moved} />}
              {data?.prompt && <PromptView prompt={data.prompt} />}
            </>
          )}
        </div>
      </div>
    </>
  );
}

const LABELS: Record<keyof Overrides, string> = {
  mode: "search mode",
  topK: "top-k",
  candidates: "candidates",
  vectorWeight: "vector weight",
  minCosine: "cosine floor",
  rerank: "reranker",
};

/** How far each passage moved since the previous result for the same question. */
function useRankChanges(data: InspectOut | undefined, question: string) {
  const previous = useRef<{ question: string; ranks: Map<number, number> } | null>(null);
  const [moved, setMoved] = useState<Map<number, number | "new">>(new Map());
  useEffect(() => {
    if (!data) return;
    const ranks = new Map(data.chunks.map((c) => [c.chunk_id, c.rank]));
    const before = previous.current?.question === data.question ? previous.current.ranks : null;
    const next = new Map<number, number | "new">();
    if (before) {
      for (const [id, rank] of ranks) {
        const old = before.get(id);
        if (old === undefined) next.set(id, "new");
        else if (old !== rank) next.set(id, old - rank);
      }
    }
    previous.current = { question: data.question, ranks };
    setMoved(next);
  }, [data, question]);
  return moved;
}

function Picker({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="space-y-1 text-sm">
      <span className="font-medium">{label}</span>
      <select
        className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {children}
      </select>
    </label>
  );
}

function Slider({
  label,
  tip,
  min,
  max,
  step,
  value,
  isDefault,
  disabled,
  onChange,
  format,
}: {
  label: string;
  tip: string;
  min: number;
  max: number;
  step: number;
  value: number;
  isDefault: boolean;
  disabled?: boolean;
  onChange: (value: number) => void;
  format: (value: number) => string;
}) {
  return (
    <label className={cn("block space-y-1.5", disabled && "opacity-50")}>
      <span className="flex items-center gap-1.5 text-sm">
        <span className="font-medium">{label}</span>
        <InfoTip label={`About ${label}`}>{tip}</InfoTip>
        <span className={cn("ml-auto tabular-nums", isDefault ? "text-muted-foreground" : "font-medium text-primary")}>
          {format(value)}
        </span>
      </span>
      <input
        type="range"
        className="w-full accent-primary"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

function Summary({ data, loading }: { data: InspectOut; loading: boolean }) {
  const t = data.timings;
  const sent = data.chunks.filter((c) => c.sent).length;
  return (
    <div className={cn("space-y-1 text-sm transition-opacity", loading && "opacity-60")}>
      <p>
        <span className="font-medium">{data.chunks.length}</span> candidates,{" "}
        <span className="font-medium">{sent}</span> sent to the model. Profile {data.profile_name} v{data.profile_version}.
      </p>
      <p className="text-xs text-muted-foreground">
        Embedding {t.embedding_cached ? "reused" : `${Math.round(t.embed_ms)} ms`} · search {Math.round(t.search_ms)} ms
        {t.rerank_ms !== null && ` · reranker ${(t.rerank_ms / 1000).toFixed(1)} s`} · total {Math.round(t.total_ms)} ms
        {loading && " · updating…"}
      </p>
      {data.expanded_question !== data.question && (
        <p className="text-xs text-muted-foreground">
          The glossary expanded the question to: <span className="text-foreground">{data.expanded_question}</span>
        </p>
      )}
    </div>
  );
}

function Results({ data, moved }: { data: InspectOut; moved: Map<number, number | "new"> }) {
  const reranked = data.parameters.rerank;
  const maxScore = Math.max(...data.chunks.map((c) => c.score), Number.EPSILON);
  const lastSent = data.chunks.filter((c) => c.sent).length;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
          <tr>
            <th className="w-14 px-3 py-2">#</th>
            <th className="px-3 py-2">Passage</th>
            <th className="w-24 px-3 py-2" title="Rank among the vector candidates · cosine similarity">
              Vector
            </th>
            <th className="w-24 px-3 py-2" title="Rank among the keyword candidates · BM25 score">
              Keyword
            </th>
            <th className="w-28 px-3 py-2" title="Reciprocal rank fusion of both lists">
              Fused
            </th>
            {reranked && (
              <th className="w-24 px-3 py-2" title="The reranker's score; it decides the order">
                Reranker
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {data.chunks.map((chunk) => (
            <ResultRow
              key={chunk.chunk_id}
              chunk={chunk}
              move={moved.get(chunk.chunk_id)}
              reranked={reranked}
              share={chunk.score / maxScore}
              lineAfter={chunk.rank === lastSent && lastSent < data.chunks.length}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ResultRow({
  chunk,
  move,
  reranked,
  share,
  lineAfter,
}: {
  chunk: InspectChunk;
  move: number | "new" | undefined;
  reranked: boolean;
  share: number;
  lineAfter: boolean;
}) {
  const [open, setOpen] = useState(false);
  const where = [chunk.page !== null && `p. ${chunk.page}`, chunk.heading].filter(Boolean).join(" · ");
  return (
    <>
      <tr className={cn("border-t align-top", !chunk.sent && "text-muted-foreground")}>
        <td className="px-3 py-2 tabular-nums">
          <div className="flex items-center gap-1">
            <span className={cn("font-medium", chunk.sent && "text-foreground")}>{chunk.rank}</span>
            <Move move={move} />
          </div>
        </td>
        <td className="px-3 py-2">
          <button type="button" className="flex w-full items-start gap-1 text-left" onClick={() => setOpen((o) => !o)}>
            {open ? <ChevronDown className="mt-0.5 size-3.5 shrink-0" /> : <ChevronRight className="mt-0.5 size-3.5 shrink-0" />}
            <span className="min-w-0">
              <span className="font-medium">{chunk.filename}</span>
              {where && <span className="text-xs text-muted-foreground"> · {where}</span>}
              <span className={cn("block text-xs text-muted-foreground", !open && "line-clamp-2")}>{chunk.text}</span>
            </span>
          </button>
        </td>
        <td className="px-3 py-2 tabular-nums">
          <Side rank={chunk.vector_rank} score={chunk.vector_score} digits={3} />
        </td>
        <td className="px-3 py-2 tabular-nums">
          <Side rank={chunk.keyword_rank} score={chunk.keyword_score} digits={2} />
        </td>
        <td className="px-3 py-2 tabular-nums">
          <span className="text-xs">{chunk.fused_score?.toFixed(4) ?? "—"}</span>
          {!reranked && (
            <span className="mt-1 block h-1 rounded-full bg-muted">
              <span className="block h-1 rounded-full bg-primary" style={{ width: `${Math.max(share * 100, 2)}%` }} />
            </span>
          )}
        </td>
        {reranked && (
          <td className="px-3 py-2 tabular-nums">
            <span className="text-xs">{chunk.rerank_score?.toFixed(3) ?? "—"}</span>
            <span className="mt-1 block h-1 rounded-full bg-muted">
              <span className="block h-1 rounded-full bg-primary" style={{ width: `${Math.max(share * 100, 2)}%` }} />
            </span>
          </td>
        )}
      </tr>
      {lineAfter && (
        <tr>
          <td colSpan={reranked ? 6 : 5} className="border-t-2 border-dashed border-primary/40 px-3 py-1 text-center text-xs text-primary">
            ↑ sent to the model · not sent ↓
          </td>
        </tr>
      )}
    </>
  );
}

function Move({ move }: { move: number | "new" | undefined }) {
  if (move === undefined) return null;
  if (move === "new") return <Badge variant="default" className="px-1.5 py-0 text-[10px]">new</Badge>;
  const up = move > 0;
  const Icon = up ? ArrowUp : ArrowDown;
  return (
    <span className={cn("flex items-center text-[10px]", up ? "text-success" : "text-destructive")} title={`Moved ${up ? "up" : "down"} ${Math.abs(move)}`}>
      <Icon className="size-3" />
      {Math.abs(move)}
    </span>
  );
}

function Side({ rank, score, digits }: { rank: number | null; score: number | null; digits: number }) {
  if (rank === null) return <span className="text-xs text-muted-foreground">—</span>;
  return (
    <span className="text-xs">
      <span className="font-medium">#{rank}</span> · {score?.toFixed(digits)}
    </span>
  );
}

function PromptView({ prompt }: { prompt: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const tokens = Math.round(prompt.length / CHARS_PER_TOKEN);
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 py-3">
        <button type="button" className="flex items-center gap-1.5 text-sm font-medium" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          Final prompt
          <span className="font-normal text-muted-foreground">
            · {prompt.length.toLocaleString()} characters, about {tokens.toLocaleString()} tokens
          </span>
        </button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            void navigator.clipboard?.writeText(prompt).then(() => {
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          <Copy className="size-3.5" /> {copied ? "Copied" : "Copy"}
        </Button>
      </CardHeader>
      {open && (
        <CardContent>
          <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs leading-relaxed">{prompt}</pre>
        </CardContent>
      )}
    </Card>
  );
}
