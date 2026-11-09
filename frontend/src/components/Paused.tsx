import { Lock, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { cn } from "@/lib/utils";
import { useTroubleshooter } from "./TroubleshooterContext";

/** Grays out a part of the page that can't work right now and says why.
 * `reason` null means it works: children render normally. */
export function Paused({
  reason,
  what,
  children,
  className,
  fill = false,
  compact = false,
}: {
  reason: string | null;
  /** What is paused, e.g. "Chat" or "Uploading documents". */
  what: string;
  children: ReactNode;
  className?: string;
  /** Keep a full-height layout (whole pages). */
  fill?: boolean;
  /** A short area (e.g. the question box): one line, centered. */
  compact?: boolean;
}) {
  const troubleshooter = useTroubleshooter();
  if (!reason) return <>{children}</>;
  return (
    <div className={cn("relative", fill && "h-full", className)}>
      <div aria-disabled="true" inert className={cn("pointer-events-none select-none opacity-40", fill && "h-full")}>
        {children}
      </div>
      <div className={cn("absolute inset-0 flex justify-center p-4", compact ? "items-center p-2" : "items-start pt-8")}>
        <div className="flex max-w-xl items-start gap-3 rounded-lg border bg-background px-4 py-3 text-sm shadow-lg">
          <Lock className="mt-0.5 size-4 shrink-0 text-warning" />
          <div className={cn(compact ? "flex flex-wrap items-center gap-x-3 gap-y-1" : "space-y-2")}>
            <p>
              <span className="font-medium">{what} is paused</span> because {reason}.
            </p>
            <Button size="sm" variant="outline" onClick={troubleshooter.open}>
              <Wrench /> Troubleshoot
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Pauses a whole page when the database or search index (or the server)
 * isn't available; the page itself pauses its own smaller parts. */
export function PageGate({ what, children }: { what: string; children: ReactNode }) {
  const status = useSystemStatus();
  return (
    <Paused reason={status.browseBlocked} what={what} fill>
      {children}
    </Paused>
  );
}
