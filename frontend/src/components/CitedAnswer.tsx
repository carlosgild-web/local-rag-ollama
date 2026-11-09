import { ChevronDown, FileText, Loader2 } from "lucide-react";
import Markdown from "react-markdown";
import type { Source } from "@/api/types";
import { useChunk } from "@/hooks/queries";
import { cn } from "@/lib/utils";

// "[1]" or "[1, 3]" not followed by "(" (so real markdown links stay links).
const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\](?!\()/g;

/** Turns citation markers into links that the renderer shows as chips. */
export function linkCitations(text: string): string {
  return text.replace(CITATION, (_, numbers: string) =>
    numbers
      .split(",")
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join(""),
  );
}

export function CitedAnswer({
  content,
  sources,
  highlighted,
  onCite,
}: {
  content: string;
  sources: Source[];
  highlighted: number | null;
  onCite: (rank: number) => void;
}) {
  const known = new Set(sources.map((s) => s.rank));
  return (
    <div className="prose-answer text-sm">
      <Markdown
        components={{
          a: ({ href, children }) => {
            const match = href?.match(/^#cite-(\d+)$/);
            if (!match) {
              return (
                <a href={href} target="_blank" rel="noreferrer" className="text-primary underline">
                  {children}
                </a>
              );
            }
            const rank = Number(match[1]);
            return (
              <button
                type="button"
                onClick={() => onCite(rank)}
                title={known.has(rank) ? sourceLabel(sources.find((s) => s.rank === rank)) : "Unknown source"}
                className={cn(
                  "mx-0.5 inline-flex h-4 min-w-4 -translate-y-1 items-center justify-center rounded px-1 align-baseline text-[10px] font-semibold",
                  known.has(rank)
                    ? "bg-primary/15 text-primary hover:bg-primary/25"
                    : "bg-muted text-muted-foreground",
                  highlighted === rank && "bg-primary text-primary-foreground",
                )}
              >
                {rank}
              </button>
            );
          },
        }}
      >
        {linkCitations(content)}
      </Markdown>
    </div>
  );
}

export function SourceList({
  sources,
  highlighted,
  onSelect,
}: {
  sources: Source[];
  highlighted: number | null;
  onSelect: (rank: number) => void;
}) {
  if (sources.length === 0) return null;
  return (
    <ol className="mt-3 space-y-1 border-t pt-3">
      {sources.map((s) => (
        <li key={s.rank}>
          <button
            type="button"
            onClick={() => onSelect(s.rank)}
            className={cn(
              "flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs text-muted-foreground transition-colors hover:bg-muted",
              highlighted === s.rank && "bg-accent text-accent-foreground ring-1 ring-primary/40",
            )}
          >
            <span className="w-5 shrink-0 font-semibold text-primary">[{s.rank}]</span>
            <FileText className="size-3.5 shrink-0" />
            <span className="truncate">{sourceLabel(s)}</span>
            <span className="ml-auto shrink-0 tabular-nums" title="Fused retrieval score (RRF)">
              {s.score.toFixed(3)}
            </span>
            <ChevronDown
              className={cn("size-3.5 shrink-0 transition-transform", highlighted === s.rank && "rotate-180")}
            />
          </button>
          {highlighted === s.rank && <Passage chunkId={s.chunk_id} />}
        </li>
      ))}
    </ol>
  );
}

function sourceLabel(s: Source | undefined): string {
  if (!s) return "";
  const parts = [s.filename ?? "deleted document"];
  if (s.page) parts.push(`page ${s.page}`);
  if (s.heading) parts.push(s.heading);
  return parts.join(" · ");
}

/** The text a citation points at, so the answer can be checked against it. */
function Passage({ chunkId }: { chunkId: number }) {
  const chunk = useChunk(chunkId);
  return (
    <div className="mx-2 mb-2 mt-1 rounded-md border bg-background px-3 py-2 text-xs">
      {chunk.isLoading && (
        <span className="flex items-center gap-1.5 text-muted-foreground">
          <Loader2 className="size-3 animate-spin" /> Loading the passage…
        </span>
      )}
      {chunk.isError && <span className="text-destructive">Could not load this passage.</span>}
      {chunk.data && (
        <>
          <p className="mb-1 text-muted-foreground">
            {chunk.data.filename} · version {chunk.data.version_number}
            {chunk.data.page ? ` · page ${chunk.data.page}` : ""}
            {chunk.data.retired && " · replaced by a later reindex (kept for this answer)"}
          </p>
          <p className="max-h-60 overflow-y-auto whitespace-pre-wrap leading-relaxed">{chunk.data.text}</p>
        </>
      )}
    </div>
  );
}
