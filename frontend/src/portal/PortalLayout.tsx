import "./portal.css";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { cn } from "@/lib/utils";
import { COMPANY } from "./content";
import { LangProvider, UI, useLang, useT } from "./i18n";
import { Logo } from "./Logo";
import { LunaBubble } from "./LunaBubble";
import { LunaProvider } from "./luna";

/** The employee portal of Hilda & Luna Beadworks, a fictional company (decision 0010). */
export default function PortalLayout() {
  return (
    <LangProvider>
      <LunaProvider>
        <Shell />
      </LunaProvider>
    </LangProvider>
  );
}

const NAV = [
  { to: "/intranet", hash: "", label: UI.nav.home, end: true },
  { to: "/intranet", hash: "#season", label: UI.nav.season },
  { to: "/intranet", hash: "#handbook", label: UI.nav.handbook },
  { to: "/intranet", hash: "#news", label: UI.nav.news },
] as const;

function Shell() {
  const t = useT();
  const location = useLocation();
  const onLunaPage = location.pathname.startsWith("/intranet/luna");
  const [menuOpen, setMenuOpen] = useState(false);
  usePortalTab(t({ es: "Intranet · Hilda & Luna", en: "Intranet · Hilda & Luna" }));

  // Scroll to a section after navigating to "/intranet#handbook" and friends.
  useEffect(() => {
    setMenuOpen(false);
    if (!location.hash) return;
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [location]);

  return (
    <div className="portal min-h-full">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-hl-card focus:px-3 focus:py-2"
      >
        {t(UI.skip)}
      </a>
      <header className="sticky top-0 z-30 bg-hl-night text-hl-moon shadow-[0_1px_0_rgba(255,255,255,0.06)]">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 sm:px-6">
          <Link to="/intranet" className="shrink-0 rounded-md" aria-label="Hilda & Luna Beadworks">
            <Logo className="h-11 w-auto" />
          </Link>
          <nav
            className={cn(
              "ml-auto items-center gap-1 text-sm max-md:absolute max-md:inset-x-0 max-md:top-full max-md:flex-col max-md:items-stretch max-md:bg-hl-night max-md:px-4 max-md:pb-4 max-md:shadow-lg",
              menuOpen ? "flex" : "hidden md:flex",
            )}
          >
            {NAV.map((item) => (
              <NavLink
                key={item.hash || "home"}
                to={{ pathname: item.to, hash: item.hash }}
                end
                className={() =>
                  cn(
                    "rounded-full px-3.5 py-2 text-hl-moon/80 transition-colors hover:bg-white/10 hover:text-white",
                    location.pathname === "/intranet" &&
                      location.hash === item.hash &&
                      "bg-white/10 text-white",
                  )
                }
              >
                {t(item.label)}
              </NavLink>
            ))}
            <NavLink
              to="/intranet/luna"
              className={({ isActive }) =>
                cn(
                  "rounded-full px-4 py-2 font-semibold transition-colors md:ml-2",
                  isActive ? "bg-hl-amber text-hl-night" : "bg-white text-hl-night hover:bg-hl-moon",
                )
              }
            >
              {t(UI.nav.luna)}
            </NavLink>
          </nav>
          <LangSwitch className="max-md:ml-auto" />
          <button
            type="button"
            className="grid size-10 place-items-center rounded-full hover:bg-white/10 md:hidden"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            aria-label={t(UI.nav.menu)}
          >
            {menuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </header>

      <main id="content">
        <ErrorBoundary area="this page">
          <Outlet />
        </ErrorBoundary>
      </main>

      {!onLunaPage && <Footer />}
      {!onLunaPage && <LunaBubble />}
    </div>
  );
}

function LangSwitch({ className }: { className?: string }) {
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

function Footer() {
  const t = useT();
  return (
    <footer className="mt-16 border-t border-hl-line bg-hl-card">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 text-sm text-hl-muted sm:flex-row sm:items-end sm:justify-between sm:px-6">
        <div className="max-w-xl space-y-1">
          <p className="font-semibold text-hl-ink">
            {COMPANY.name} · {COMPANY.city}
          </p>
          <p>{t(UI.footer.fictional)}</p>
          <p>{t(UI.footer.local)}</p>
        </div>
        <a href="/" className="inline-flex items-center gap-1 font-semibold text-hl-cobalt hover:underline">
          {t(UI.footer.console)} <ArrowUpRight className="size-4" />
        </a>
      </div>
    </footer>
  );
}

/** The portal gets its own tab title and bead-moon favicon while it is open. */
function usePortalTab(title: string) {
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
