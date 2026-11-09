import { X } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

/** A modal dialog (shadcn/ui look, no extra dependency): closes on Escape,
 * on the backdrop and on the ✕; focus moves into it when it opens.
 * `side="right"` shows it as a full-height drawer instead of a centred box. */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
  side = "center",
  closeLabel = "Close",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  side?: "center" | "right";
  closeLabel?: string;
}) {
  const panel = useRef<HTMLDivElement>(null);
  // Callers usually pass a new onClose on every render. Keep the latest in a
  // ref so the effect below runs only when the dialog opens: re-running it
  // moved focus to the panel after each keystroke in the dialog's fields.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeRef.current();
    document.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  if (!open) return null;
  return createPortal(
    <div
      className={cn(
        "fixed inset-0 z-50 flex bg-black/40",
        side === "right" ? "justify-end" : "items-start justify-center overflow-y-auto p-4 sm:p-10",
      )}
    >
      <button type="button" aria-label={closeLabel} className="fixed inset-0 cursor-default" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          "relative z-10 flex w-full flex-col border bg-background shadow-xl outline-none",
          side === "right" ? "dialog-drawer h-full max-w-md border-y-0 border-r-0" : "max-h-full max-w-2xl rounded-lg",
          className,
        )}
      >
        <div className="flex items-start gap-4 border-b px-6 py-4">
          <div className="flex-1">
            <h2 className="text-lg font-semibold">{title}</h2>
            {description && <div className="mt-1 text-sm text-muted-foreground">{description}</div>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-muted"
            title={closeLabel}
            aria-label={closeLabel}
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="overflow-y-auto px-6 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t px-6 py-3">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
