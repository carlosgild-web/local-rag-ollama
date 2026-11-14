import { BookA, Loader2 } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { useDemo, useGlossaryMutation } from "@/hooks/queries";
import { cn } from "@/lib/utils";

const DISMISS_KEY = "glossary-notice-dismissed";

function dismissed(): boolean {
  try {
    return localStorage.getItem(DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * The demo company was loaded before v0.9.0 added the glossary, so its words
 * are missing and a question about "vacation" doesn't find the PTO policy.
 * Offers them with one click; never loads them by itself. `dismissible` lets
 * the Dashboard's copy be hidden; the Glossary card's copy always shows.
 */
export function GlossaryNotice({ dismissible = false, className }: { dismissible?: boolean; className?: string }) {
  const demo = useDemo();
  const load = useGlossaryMutation(() => api.loadDemoGlossary());
  const [hidden, setHidden] = useState(() => dismissible && dismissed());
  if (!demo.data?.glossary_missing || hidden) return null;

  const hide = () => {
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // private window: hide for this visit only
    }
    setHidden(true);
  };

  return (
    <div className={cn("flex flex-wrap items-start gap-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm", className)}>
      <BookA className="mt-0.5 size-4 shrink-0 text-warning" />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium">The demo library is loaded, but its glossary isn't.</p>
        <p className="text-muted-foreground">
          It was loaded before the glossary existed. Without it, a question about <q>vacation days</q> doesn't find the PTO
          policy and answers "not found". The glossary adds 8 of the demo company's words; you can remove any of them later.
        </p>
        <ErrorNote error={load.error} />
      </div>
      <div className="flex gap-2">
        {dismissible && (
          <Button variant="ghost" size="sm" onClick={hide}>
            Not now
          </Button>
        )}
        <Button size="sm" onClick={() => load.mutate(undefined)} disabled={load.isPending}>
          {load.isPending && <Loader2 className="animate-spin" />} Load the words
        </Button>
      </div>
    </div>
  );
}
