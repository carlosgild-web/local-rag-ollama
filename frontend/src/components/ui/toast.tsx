import { CheckCircle2, X, XCircle } from "lucide-react";
import { useEffect } from "react";
import { cn } from "@/lib/utils";

export interface ToastMessage {
  id: number;
  tone: "success" | "error" | "warning";
  text: string;
}

/** Small notices in the bottom-right corner that close themselves. */
export function Toasts({ toasts, onDismiss }: { toasts: ToastMessage[]; onDismiss: (id: number) => void }) {
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onDismiss={() => onDismiss(toast.id)} />
      ))}
    </div>
  );
}

function Toast({ toast, onDismiss }: { toast: ToastMessage; onDismiss: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 8000);
    return () => clearTimeout(timer);
  }, [onDismiss]);
  const Icon = toast.tone === "success" ? CheckCircle2 : XCircle;
  return (
    <div
      role="status"
      className={cn(
        "pointer-events-auto flex items-start gap-2 rounded-lg border bg-background px-3 py-2.5 text-sm shadow-lg",
        toast.tone === "success" && "border-success/40",
        toast.tone === "error" && "border-destructive/40",
        toast.tone === "warning" && "border-warning/40",
      )}
    >
      <Icon
        className={cn(
          "mt-0.5 size-4 shrink-0",
          toast.tone === "success" && "text-success",
          toast.tone === "error" && "text-destructive",
          toast.tone === "warning" && "text-warning",
        )}
      />
      <span className="flex-1">{toast.text}</span>
      <button type="button" onClick={onDismiss} className="text-muted-foreground hover:text-foreground" title="Close">
        <X className="size-3.5" />
      </button>
    </div>
  );
}
