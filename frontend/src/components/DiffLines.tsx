import { cn } from "@/lib/utils";

/** A unified text diff, readable: added lines green, removed lines red and struck through,
 * gaps between changes as "⋯". Used by version compare and the near-duplicate preview. */
export function DiffLines({ diff, empty = "The text is the same." }: { diff: string[]; empty?: string }) {
  const lines = diff.filter((l) => !l.startsWith("---") && !l.startsWith("+++"));
  const added = lines.filter((l) => l.startsWith("+")).length;
  const removed = lines.filter((l) => l.startsWith("-")).length;
  if (lines.length === 0) {
    return <p className="rounded-md border bg-muted/30 p-3 text-sm">{empty}</p>;
  }
  return (
    <div className="space-y-2">
      <p className="text-sm">
        <span className="text-success">
          {added} line{added === 1 ? "" : "s"} added
        </span>{" "}
        · <span className="text-destructive">{removed} removed</span>
      </p>
      <div className="max-h-[60vh] overflow-auto rounded-md border font-mono text-xs leading-relaxed">
        {lines.map((line, i) =>
          line.startsWith("@@") ? (
            <div key={i} className="border-y bg-muted px-3 py-0.5 text-muted-foreground">
              ⋯
            </div>
          ) : (
            <div
              key={i}
              className={cn(
                "whitespace-pre-wrap px-3",
                line.startsWith("+") && "bg-green-50 text-green-900",
                line.startsWith("-") && "bg-red-50 text-red-900 line-through decoration-red-300",
              )}
            >
              <span className="mr-2 select-none opacity-60">{line[0] === " " ? " " : line[0]}</span>
              {line.slice(1)}
            </div>
          ),
        )}
      </div>
    </div>
  );
}
