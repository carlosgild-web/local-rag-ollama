/**
 * Pieces shared by the two Hilda & Luna layouts: the intranet (decision 0010)
 * and the public website (decision 0011).
 */
import { useEffect } from "react";
import { cn } from "@/lib/utils";
import { UI, useLang, useT } from "./i18n";

/** ES / EN pills, styled for a dark bar. The choice is remembered for both sites. */
export function LangSwitch({ className }: { className?: string }) {
  const { lang, setLang } = useLang();
  const t = useT();
  return (
    <div role="group" aria-label={t(UI.langLabel)} className={cn("flex rounded-full bg-white/10 p-0.5 text-xs font-semibold", className)}>
      {(["es", "en"] as const).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          lang={code}
          title={code === "es" ? "Español" : "English"}
          className={cn(
            "rounded-full px-2.5 py-1.5 uppercase tracking-wider transition-colors",
            lang === code ? "bg-hl-moon text-hl-night" : "text-hl-moon/70 hover:text-white",
          )}
        >
          {code}
        </button>
      ))}
    </div>
  );
}

/** Gives the page its own tab title and the bead-moon favicon while it is open. */
export function useBrandTab(title: string) {
  useEffect(() => {
    const icon = document.querySelector<HTMLLinkElement>("link[rel='icon']");
    const previous = { title: document.title, icon: icon?.href };
    document.title = title;
    if (icon) icon.href = "/hl-mark.svg";
    return () => {
      document.title = previous.title;
      if (icon && previous.icon) icon.href = previous.icon;
    };
  }, [title]);
}
