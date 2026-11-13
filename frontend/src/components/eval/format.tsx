import type { EvalChange, EvalMetrics } from "@/api/types";
import { Badge } from "@/components/ui/badge";

export type MetricKind = "pct" | "num" | "ms";

/** The run totals in the order they're shown. `answers` ones need generated answers. */
export const METRICS: { key: keyof EvalMetrics; label: string; kind: MetricKind; hint: string; answers?: boolean }[] =
  [
    { key: "hit_rate_at_5", label: "Hit rate@5", kind: "pct", hint: "An expected file is among the first 5 passages" },
    { key: "mrr", label: "MRR", kind: "num", hint: "1 / rank of the first passage from an expected file, averaged" },
    { key: "pass_rate", label: "Passed", kind: "pct", hint: "Cases that passed every check that ran" },
    {
      key: "answered_rate",
      label: "Answered",
      kind: "pct",
      hint: "Questions with an answer in the documents that didn't get 'not found'",
      answers: true,
    },
    { key: "facts_rate", label: "Facts", kind: "pct", hint: "Answers with every required fact", answers: true },
    {
      key: "trap_rate",
      label: "'Not found' right",
      kind: "pct",
      hint: "Questions whose answer isn't on the shelf that got 'not found'",
      answers: true,
    },
    {
      key: "citation_rate",
      label: "Citations",
      kind: "pct",
      hint: "Answers whose citations all point at an expected file",
      answers: true,
    },
    {
      key: "faithfulness",
      label: "Faithful",
      kind: "num",
      hint: "The judge model's score: 1 every fact is in the sources, 0.5 some, 0 none",
      answers: true,
    },
    {
      key: "variant_rate",
      label: "Wordings",
      kind: "pct",
      hint: "Groups of the same question in other words where every wording passed",
    },
  ];

export function formatMetric(value: number | null | undefined, kind: MetricKind): string {
  if (value === null || value === undefined) return "–";
  if (kind === "pct") return `${Math.round(value * 100)}%`;
  if (kind === "ms") return value >= 10_000 ? `${(value / 1000).toFixed(0)} s` : `${Math.round(value)} ms`;
  return value.toFixed(2);
}

/** "+4 pts" for rates, "+0.05" for scores; positive is better for every metric. */
export function formatDelta(a: number | null | undefined, b: number | null | undefined, kind: MetricKind) {
  if (a === null || a === undefined || b === null || b === undefined) return null;
  const diff = b - a;
  if (Math.abs(diff) < 1e-9) return { text: "=", tone: "text-muted-foreground" };
  const text = kind === "pct" ? `${diff > 0 ? "+" : ""}${Math.round(diff * 100)} pts` : `${diff > 0 ? "+" : ""}${diff.toFixed(2)}`;
  return { text, tone: diff > 0 ? "text-success" : "text-destructive" };
}

export function PassBadge({ passed, error }: { passed: boolean | null; error?: string | null }) {
  if (error) return <Badge variant="destructive">error</Badge>;
  if (passed === null) return <Badge variant="secondary">–</Badge>;
  return passed ? <Badge variant="success">pass</Badge> : <Badge variant="destructive">fail</Badge>;
}

const CHANGE: Record<EvalChange, { label: string; variant: "success" | "destructive" | "secondary" | "outline" }> = {
  fixed: { label: "fixed", variant: "success" },
  better: { label: "ranked higher", variant: "success" },
  broken: { label: "broke", variant: "destructive" },
  worse: { label: "ranked lower", variant: "destructive" },
  same: { label: "same", variant: "secondary" },
  only_a: { label: "only in A", variant: "outline" },
  only_b: { label: "only in B", variant: "outline" },
};

export function ChangeBadge({ change }: { change: EvalChange }) {
  const { label, variant } = CHANGE[change];
  return <Badge variant={variant}>{label}</Badge>;
}

export const MODE_LABEL = { hybrid: "Hybrid", vector: "Vectors only", keyword: "Keywords only" } as const;

export function rankText(rank: number | null): string {
  return rank === null ? "not found" : `#${rank}`;
}
