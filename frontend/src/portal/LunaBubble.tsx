import { Maximize2, Plus, X } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { UI, useT } from "./i18n";
import { LogoMark } from "./Logo";
import { LunaChat } from "./LunaChat";
import { useLuna } from "./luna";

/** The floating chat: a bead-moon button that opens a compact Luna panel. */
export function LunaBubble() {
  const t = useT();
  const luna = useLuna();
  const navigate = useNavigate();
  const button = useRef<HTMLButtonElement>(null);
  const open = luna.bubbleOpen;

  useEffect(() => {
    if (!open) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        luna.setBubbleOpen(false);
        button.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, luna]);

  return (
    <div
      className="fixed z-40 flex flex-col items-end gap-3"
      style={{
        right: "max(16px, calc(env(safe-area-inset-right, 0px) + 16px))",
        bottom: "max(16px, calc(env(safe-area-inset-bottom, 0px) + 16px))",
      }}
    >
      {open && (
        <section
          role="dialog"
          aria-label={`${UI.luna.name} · ${t(UI.luna.tagline)}`}
          className="flex h-[min(600px,calc(100dvh-112px))] w-[min(400px,calc(100vw-32px))] flex-col overflow-hidden rounded-3xl bg-hl-card shadow-2xl ring-1 ring-hl-line"
        >
          <header className="flex items-center gap-3 bg-hl-night px-4 py-3 text-hl-moon">
            <LogoMark className="size-9" />
            <div className="min-w-0 flex-1">
              <p className="font-display text-lg leading-tight">{UI.luna.name}</p>
              <p className="truncate text-xs text-hl-moon/70">{t(UI.luna.tagline)}</p>
            </div>
            <HeaderButton label={t(UI.luna.newChat)} onClick={luna.newChat}>
              <Plus className="size-4" />
            </HeaderButton>
            <HeaderButton
              label={t(UI.luna.expand)}
              onClick={() => {
                luna.setBubbleOpen(false);
                navigate("/intranet/luna");
              }}
            >
              <Maximize2 className="size-4" />
            </HeaderButton>
            <HeaderButton label={t(UI.luna.close)} onClick={() => luna.setBubbleOpen(false)}>
              <X className="size-4" />
            </HeaderButton>
          </header>
          <div className="min-h-0 flex-1 bg-hl-paper">
            <LunaChat variant="panel" autoFocus />
          </div>
        </section>
      )}
      <button
        ref={button}
        type="button"
        onClick={() => luna.setBubbleOpen(!open)}
        aria-expanded={open}
        aria-label={open ? t(UI.luna.close) : t(UI.luna.open)}
        className={cn(
          "group flex items-center gap-2 rounded-full bg-hl-night py-2 pl-2 text-hl-moon shadow-xl ring-1 ring-white/10 transition-transform hover:-translate-y-0.5",
          open ? "pr-2" : "pr-5",
        )}
      >
        <span className="grid size-11 place-items-center rounded-full bg-hl-night-2">
          {open ? <X className="size-5" /> : <LogoMark className="size-10" />}
        </span>
        {!open && <span className="font-display text-base">{t(UI.nav.luna)}</span>}
        {luna.isStreaming && !open && (
          <span className="absolute right-1 top-1 size-3 animate-pulse rounded-full bg-hl-amber ring-2 ring-hl-night" />
        )}
      </button>
    </div>
  );
}

function HeaderButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="grid size-8 place-items-center rounded-full text-hl-moon/80 transition-colors hover:bg-white/10 hover:text-white"
    >
      {children}
    </button>
  );
}
