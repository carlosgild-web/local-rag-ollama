import { X } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

/** A modal dialog (shadcn/ui look, no extra dependency): closes on Escape,
 * on the backdrop and on the ✕; focus moves into it when it opens. */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:p-10">
      <button type="button" aria-label="Close" className="fixed inset-0 cursor-default" onClick={onClose} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          "relative z-10 flex max-h-full w-full max-w-2xl flex-col rounded-lg border bg-background shadow-xl outline-none",
          className,
        )}
      >
        <div className="flex items-start gap-4 border-b px-6 py-4">
          <div className="flex-1">
            <h2 className="text-lg font-semibold">{title}</h2>
            {description && <div className="mt-1 text-sm text-muted-foreground">{description}</div>}
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted" title="Close">
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
