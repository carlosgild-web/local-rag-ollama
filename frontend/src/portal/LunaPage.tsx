import { MessageCircle, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { UI, useT } from "./i18n";
import { LogoMark } from "./Logo";
import { LunaChat } from "./LunaChat";
import { useLuna } from "./luna";

/** Luna, full screen: recent conversations on the side, the chat in the middle. */
export default function LunaPage() {
  const t = useT();
  const luna = useLuna();

  return (
    <div className="mx-auto grid h-[calc(100dvh-68px)] max-w-6xl grid-cols-1 gap-6 px-4 sm:px-6 lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="hidden flex-col gap-4 py-6 lg:flex">
        <div className="flex items-center gap-3">
          <span className="grid size-12 place-items-center rounded-2xl bg-hl-night text-hl-moon">
            <LogoMark className="size-10" />
          </span>
          <div>
            <h1 className="font-display text-2xl leading-none">{UI.luna.name}</h1>
            <p className="mt-1 text-xs text-hl-muted">{t(UI.luna.tagline)}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={luna.newChat}
          className="flex items-center justify-center gap-2 rounded-xl bg-hl-cobalt px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
        >
          <Plus className="size-4" /> {t(UI.luna.newChat)}
        </button>
        {luna.recent.length > 0 && (
          <nav aria-label={t(UI.luna.recent)} className="min-h-0 flex-1 overflow-y-auto">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-hl-muted">{t(UI.luna.recent)}</p>
            <ul className="flex flex-col gap-0.5">
              {luna.recent.map((chat) => (
                <li key={chat.id}>
                  <button
                    type="button"
                    onClick={() => luna.openChat(chat.id)}
                    aria-current={chat.id === luna.sessionId ? "true" : undefined}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-hl-card",
                      chat.id === luna.sessionId && "bg-hl-card font-semibold shadow-sm ring-1 ring-hl-line",
                    )}
                  >
                    <MessageCircle className="size-4 shrink-0 text-hl-muted" />
                    <span className="truncate">{chat.title}</span>
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-2 px-3 text-[11px] text-hl-muted">{t(UI.luna.recentNote)}</p>
          </nav>
        )}
      </aside>

      <section className="flex min-h-0 flex-col">
        <div className="flex items-center justify-between gap-3 pt-4 lg:hidden">
          <h1 className="font-display text-2xl">{UI.luna.name}</h1>
          <button
            type="button"
            onClick={luna.newChat}
            className="flex items-center gap-1.5 rounded-full bg-hl-card px-3 py-1.5 text-sm font-semibold ring-1 ring-hl-line"
          >
            <Plus className="size-4" /> {t(UI.luna.newChat)}
          </button>
        </div>
        <div className="min-h-0 flex-1">
          <LunaChat variant="page" autoFocus />
        </div>
      </section>
    </div>
  );
}
