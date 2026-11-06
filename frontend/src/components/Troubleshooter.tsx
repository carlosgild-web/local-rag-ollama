import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Database,
  Download,
  ListTodo,
  Loader2,
  MinusCircle,
  RefreshCw,
  Search,
  Server,
  Wrench,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { postEventStream } from "@/api/sse";
import type { CheckStatus, DiagnosticAction, DiagnosticCheck } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { useDiagnostics } from "@/hooks/queries";
import { cn, formatDate } from "@/lib/utils";

const COMPONENTS = [
  { key: "ollama", label: "Ollama (the AI models)", icon: Server },
  { key: "sqlite", label: "Database (documents, chats, settings)", icon: Database },
  { key: "vector_store", label: "Search index", icon: Search },
  { key: "jobs", label: "Background jobs", icon: ListTodo },
] as const;

const STATUS_ICON: Record<CheckStatus, typeof CheckCircle2> = {
  ok: CheckCircle2,
  warn: AlertTriangle,
  fail: XCircle,
  skip: MinusCircle,
};

const STATUS_COLOR: Record<CheckStatus, string> = {
  ok: "text-success",
  warn: "text-warning",
  fail: "text-destructive",
  skip: "text-muted-foreground",
};

const SUMMARY = {
  ok: "Everything looks fine.",
  warn: "The app works, but something may cause problems.",
  fail: "Something is broken. Start with the first red item below.",
};

/** The troubleshooting panel: runs every check and shows what is wrong, the
 * likely cause and what to do, with buttons for the fixes the app can do. */
export function Troubleshooter({ open, onClose }: { open: boolean; onClose: () => void }) {
  const diagnostics = useDiagnostics(open);
  const report = diagnostics.data;
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          <Wrench className="size-5" /> Troubleshooting
        </span>
      }
      description={
        report ? `${SUMMARY[report.status]} Checked ${formatDate(report.ran_at)}.` : "Checking every part of the app…"
      }
      footer={
        <>
          <Button variant="outline" onClick={() => diagnostics.refetch()} disabled={diagnostics.isFetching}>
            <RefreshCw className={cn(diagnostics.isFetching && "animate-spin")} /> Run checks again
          </Button>
          <Button onClick={onClose}>Close</Button>
        </>
      }
    >
      {report && report.simulated.length > 0 && (
        <div className="mb-4 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          Test mode: these faults are simulated on purpose (SIMULATE_FAULTS = {report.simulated.join(", ")}). Nothing
          is really broken.
        </div>
      )}
      <ErrorNote error={diagnostics.error} />
      {diagnostics.isLoading && (
        <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Running checks…
        </p>
      )}
      {report && (
        <div className="space-y-5">
          {COMPONENTS.map(({ key, label, icon: Icon }) => {
            const checks = report.checks.filter((c) => c.component === key);
            if (checks.length === 0) return null;
            const order: CheckStatus[] = ["fail", "warn", "ok", "skip"];
            const worst = order.find((s) => checks.some((c) => c.status === s)) ?? "ok";
            const WorstIcon = STATUS_ICON[worst];
            return (
              <section key={key}>
                <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                  <Icon className="size-4 text-muted-foreground" /> {label}
                  <WorstIcon className={cn("ml-auto size-4", STATUS_COLOR[worst])} />
                </h3>
                <ul className="space-y-1.5">
                  {checks.map((check) => (
                    <CheckRow key={check.id} check={check} onDone={() => diagnostics.refetch()} onClose={onClose} />
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </Dialog>
  );
}

function CheckRow({ check, onDone, onClose }: { check: DiagnosticCheck; onDone: () => void; onClose: () => void }) {
  const Icon = STATUS_ICON[check.status];
  const problem = check.status === "fail" || check.status === "warn";
  return (
    <li
      className={cn(
        "rounded-md px-3 py-2 text-sm",
        problem && "border",
        check.status === "fail" && "border-destructive/30 bg-destructive/5",
        check.status === "warn" && "border-warning/30 bg-warning/5",
      )}
    >
      <div className="flex items-start gap-2">
        <Icon className={cn("mt-0.5 size-4 shrink-0", STATUS_COLOR[check.status])} />
        <div className="min-w-0 flex-1">
          <div className="font-medium">{check.title}</div>
          <div className="break-words text-muted-foreground">{check.detail}</div>
          {problem && (
            <div className="mt-2 space-y-1.5">
              {check.cause && (
                <p>
                  <span className="font-medium">Likely cause: </span>
                  {check.cause}
                </p>
              )}
              {check.fix && (
                <p>
                  <span className="font-medium">What to do: </span>
                  {check.fix}
                </p>
              )}
              {check.commands.map((command) => (
                <CommandLine key={command} command={command} />
              ))}
              {check.action && <ActionButton action={check.action} onDone={onDone} onClose={onClose} />}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-2 rounded bg-muted px-2 py-1 font-mono text-xs">
      <span className="flex-1 break-all">{command}</span>
      <button
        type="button"
        title="Copy the command"
        className="text-muted-foreground hover:text-foreground"
        onClick={async () => {
          await navigator.clipboard.writeText(command);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? <CheckCircle2 className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
      </button>
    </div>
  );
}

type PullEvent =
  | { event: "progress"; data: { status: string; total?: number; completed?: number } }
  | { event: "done"; data: { name: string } }
  | { event: "error"; data: { detail: string } };

/** Runs a fix the app can do itself: download a model, queue a reindex, or
 * take the user to the page where they can act. */
function ActionButton({
  action,
  onDone,
  onClose,
}: {
  action: DiagnosticAction;
  onDone: () => void;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setError(null);
    if (action.kind === "open_queue" || action.kind === "open_collections") {
      onClose();
      navigate(action.kind === "open_queue" ? "/queue" : "/collections");
      return;
    }
    setBusy(true);
    try {
      if (action.kind === "reindex_collection" && action.target) {
        await api.reindexCollection(Number(action.target));
        setMessage("Reindex queued. It runs in the background; run the checks again when it's done.");
        client.invalidateQueries({ queryKey: ["jobs"] });
      } else if (action.kind === "pull_model" && action.target) {
        for await (const event of postEventStream<PullEvent>("/models/pull", { name: action.target })) {
          if (event.event === "progress") {
            const { status, total, completed } = event.data;
            const pct = total && completed ? ` ${Math.round((completed / total) * 100)}%` : "";
            setMessage(`${status}${pct}`);
          } else if (event.event === "error") {
            throw new Error(event.data.detail);
          } else {
            setMessage(`${action.target} is installed.`);
          }
        }
        onDone();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-1">
      <Button size="sm" onClick={run} disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : action.kind === "pull_model" ? <Download /> : <Wrench />}
        {action.label}
      </Button>
      {message && <p className="text-xs text-muted-foreground">{message}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
