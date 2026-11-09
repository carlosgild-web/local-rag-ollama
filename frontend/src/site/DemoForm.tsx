import { Info } from "lucide-react";
import { type FormEvent, type ReactNode, useId, useState } from "react";
import { cn } from "@/lib/utils";
import { useT } from "@/portal/i18n";
import { DEMO_FORM } from "./content";

/**
 * A form that looks real but never leaves the page (decision 0011): the
 * browser still checks required fields, then the form clears and says that
 * nothing was sent. No request is made and nothing is stored.
 */
export function DemoForm({
  children,
  submit,
  className,
  tone = "light",
}: {
  children: ReactNode;
  submit: string;
  className?: string;
  tone?: "light" | "dark";
}) {
  const t = useT();
  const [sent, setSent] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    event.currentTarget.reset();
    setSent(true);
  };

  return (
    <form onSubmit={onSubmit} onChange={() => setSent(false)} className={className}>
      {children}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          className={cn(
            "rounded-full px-5 py-2.5 font-semibold transition-opacity hover:opacity-90",
            tone === "dark" ? "bg-hl-amber text-hl-bark" : "bg-hl-rust text-white",
          )}
        >
          {submit}
        </button>
        <p
          role="status"
          aria-live="polite"
          className={cn(
            "flex items-center gap-1.5 text-sm",
            tone === "dark" ? "text-hl-cream/90" : "text-hl-bark-muted",
            !sent && "sr-only",
          )}
        >
          {sent && (
            <>
              <Info className="size-4 shrink-0" /> {t(DEMO_FORM.sent)}
            </>
          )}
        </p>
      </div>
    </form>
  );
}

/** A labeled field for the demo forms. */
export function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: (id: string) => ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children(id)}
    </div>
  );
}
