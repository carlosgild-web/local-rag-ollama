import { FileText } from "lucide-react";
import Markdown from "react-markdown";
import type { Source } from "@/api/types";
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
          </button>
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
