import { Info } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** An ⓘ that explains a setting on hover or keyboard focus (shadcn look, no
 * extra dependency). */
export function InfoTip({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <span className={cn("group relative inline-flex align-middle", className)}>
      <button
        type="button"
        aria-label={label}
        className="rounded-full text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Info className="size-3.5" />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-full -left-3 z-30 mb-2 w-72 rounded-md bg-foreground px-3 py-2 text-xs font-normal leading-relaxed text-background opacity-0 shadow-lg transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        {children}
      </span>
    </span>
  );
}
