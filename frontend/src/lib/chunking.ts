import type { Model } from "@/api/types";

/** What the server accepts (CollectionIn / CollectionReindexIn). */
export const LIMITS = { minSize: 50, maxSize: 4000, maxOverlapPct: 49 } as const;

export interface Preset {
  id: string;
  label: string;
  hint: string;
  size: number;
  overlapPct: number;
}

export const PRESETS: Preset[] = [
  { id: "short", label: "Short facts", hint: "FAQs, price lists, tables", size: 300, overlapPct: 10 },
  { id: "balanced", label: "Balanced (recommended)", hint: "most documents", size: 600, overlapPct: 12 },
  { id: "long", label: "Long text", hint: "manuals, contracts, reports", size: 1000, overlapPct: 15 },
];

export interface Advice {
  level: "error" | "warning";
  field: "size" | "overlap" | "model";
  text: string;
}

/** Plain-language checks on the reading settings. Errors are values the
 * server would reject; warnings are allowed but rarely what you want. */
export function adviseSettings(size: string, overlap: string, model: string, models: Model[]): Advice[] {
  const out: Advice[] = [];
  if (size !== "") {
    const n = Number(size);
    if (!Number.isInteger(n) || n < LIMITS.minSize || n > LIMITS.maxSize)
      out.push({
        level: "error",
        field: "size",
        text: `Chunk size must be a whole number from ${LIMITS.minSize} to ${LIMITS.maxSize} tokens.`,
      });
    else if (n < 150)
      out.push({
        level: "warning",
        field: "size",
        text: `Pieces of ${n} tokens hold only a sentence or two: answers would miss the context around a fact. 300–1000 suits most documents.`,
      });
    else if (n > 1500)
      out.push({
        level: "warning",
        field: "size",
        text: `Pieces of ${n} tokens mix several topics: search gets less precise, and fewer pieces fit in the question sent to the model.`,
      });
  }
  if (overlap !== "") {
    const n = Number(overlap);
    if (!Number.isFinite(n) || n < 0 || n > LIMITS.maxOverlapPct)
      out.push({ level: "error", field: "overlap", text: `Overlap must be from 0 to ${LIMITS.maxOverlapPct}%.` });
    else if (n === 0)
      out.push({
        level: "warning",
        field: "overlap",
        text: "With no overlap, a sentence split between two pieces is never seen whole. 10–15% avoids that.",
      });
    else if (n > 30)
      out.push({
        level: "warning",
        field: "overlap",
        text: `${n}% overlap stores much of each document twice: slower to build, and search returns near-duplicates.`,
      });
  }
  const info = models.find((m) => m.name === model || m.name === `${model}:latest`);
  if (model && info && info.capabilities.length > 0 && !info.capabilities.includes("embedding"))
    out.push({
      level: "error",
      field: "model",
      text: `${model} is a chat model, not an embedding model: it can't turn text into search vectors. Pick bge-m3 or another embedding model.`,
    });
  return out;
}
