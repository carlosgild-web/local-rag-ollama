import "./site.css";
import { ArrowUpRight, Lock, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { cn } from "@/lib/utils";
import { LangSwitch, useBrandTab } from "@/portal/brand";
import { DemoGuide } from "@/portal/DemoGuide";
import { LangProvider, useT } from "@/portal/i18n";
import { Logo } from "@/portal/Logo";
import { ANNOUNCE, FOOTER, NAV, SITE } from "./content";

/** The public website of Hilda & Luna Beadworks, a fictional company (decision 0011). */
export default function SiteLayout() {
  return (
    <LangProvider>
      <Shell />
    </LangProvider>
  );
}

const LINKS = [
  { to: "/site", label: NAV.home, end: true },
  { to: "/site/catalog", label: NAV.catalog },
  { to: "/site/wholesale", label: NAV.wholesale },
  { to: "/site/help", label: NAV.help },
] as const;

function Shell() {
  const t = useT();
  const { pathname, hash } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  useBrandTab(t(NAV.tab));

  // A new page starts at the top; "/site/help#returns" scrolls to its section.
  useEffect(() => {
    setMenuOpen(false);
    if (!hash) {
      window.scrollTo({ top: 0 });
      return;
    }
    // The page may still be loading its chunk: look for the section for up to ~2 s.
    let tries = 0;
    let frame = 0;
    const find = () => {
      const target = document.getElementById(hash.slice(1));
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      else if (tries++ < 120) frame = requestAnimationFrame(find);
    };
    find();
    return () => cancelAnimationFrame(frame);
  }, [pathname, hash]);

  const staffPage = pathname.startsWith("/site/staff");

  return (
    <div className="site min-h-full">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2"
      >
        {t(NAV.skip)}
      </a>

      <DemoGuide where="site" />
      <div className="bg-hl-bark text-hl-cream">
        <div className="mx-auto flex max-w-6xl items-center gap-x-4 gap-y-1 px-4 py-1.5 text-xs sm:px-6">
          <p className="hidden text-hl-cream/75 sm:block">{t(NAV.tagline)}</p>
          <div className="ml-auto flex items-center gap-1 sm:gap-3">
            <Link to="/site/wholesale" className="hidden rounded-full px-2 py-1.5 font-medium text-hl-cream/85 hover:text-white sm:inline">
              {t(NAV.wholesaleAccounts)}
            </Link>
            <Link
              to="/site/staff"
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1.5 font-semibold transition-colors hover:bg-white/10",
                staffPage ? "bg-white/10 text-white" : "text-hl-cream",
              )}
            >
              <Lock className="size-3.5" /> {t(NAV.employeeLogin)}
            </Link>
            <LangSwitch />
          </div>
        </div>
      </div>

      <header className="sticky top-0 z-30 border-b border-hl-clay bg-hl-cream/95 backdrop-blur">
        <div className="relative mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 sm:px-6">
          <Link to="/site" className="shrink-0 rounded-md text-hl-bark" aria-label={SITE.name}>
            <Logo className="h-11 w-auto" />
          </Link>
          <nav
            aria-label={t(NAV.menu)}
            className={cn(
              "ml-auto items-center gap-1 text-[0.95rem] max-md:absolute max-md:inset-x-0 max-md:top-full max-md:flex-col max-md:items-stretch max-md:border-b max-md:border-hl-clay max-md:bg-hl-cream max-md:px-4 max-md:pb-4 max-md:shadow-lg",
              menuOpen ? "flex" : "hidden md:flex",
            )}
          >
            {LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={"end" in link}
                className={({ isActive }) =>
                  cn(
                    "rounded-full px-3.5 py-2 font-medium transition-colors hover:bg-hl-sand",
                    isActive ? "bg-hl-sand text-hl-rust" : "text-hl-bark",
                  )
                }
              >
                {t(link.label)}
              </NavLink>
            ))}
          </nav>
          <button
            type="button"
            className="ml-auto grid size-10 place-items-center rounded-full hover:bg-hl-sand md:hidden"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            aria-label={t(NAV.menu)}
          >
            {menuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </header>

      {!staffPage && (
        <div className="border-b border-hl-clay bg-hl-sand/70">
          <p className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-3 gap-y-0.5 px-4 py-2 text-center text-sm sm:px-6">
            <Link to="/site/catalog" className="font-semibold text-hl-rust hover:underline">
              {t(ANNOUNCE.collection)}
            </Link>
            <span aria-hidden="true" className="text-hl-bark-muted max-sm:hidden">
              ·
            </span>
            <span className="text-hl-bark-muted">{t(ANNOUNCE.shipping)}</span>
          </p>
        </div>
      )}

      <main id="content">
        <ErrorBoundary area="this page">
          <Outlet />
        </ErrorBoundary>
      </main>

      <Footer />
    </div>
  );
}

function Footer() {
  const t = useT();
  const columns = [
    {
      title: FOOTER.care,
      links: [
        { to: "/site/help#shipping", label: FOOTER.shipping },
        { to: "/site/help#returns", label: FOOTER.returns },
        { to: "/site/help#faq", label: FOOTER.faq },
        { to: "/site/help#contact", label: FOOTER.contact },
      ],
    },
    {
      title: FOOTER.company,
      links: [
        { to: "/site#story", label: NAV.story },
        { to: "/site/catalog", label: NAV.catalog },
        { to: "/site/wholesale", label: NAV.wholesale },
      ],
    },
    {
      title: FOOTER.employees,
      links: [
        { to: "/site/staff", label: FOOTER.staff },
        { to: "/intranet", label: FOOTER.intranet },
      ],
    },
  ];
  return (
    <footer className="mt-20 bg-hl-bark text-hl-cream">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))]">
        <div className="space-y-3 text-sm text-hl-cream/75">
          <Logo className="h-12 w-auto text-hl-cream" />
          <p>
            {SITE.address} · {SITE.city}
          </p>
          <p>
            <a href={`mailto:${SITE.support}`} className="hover:text-white hover:underline">
              {SITE.support}
            </a>
          </p>
        </div>
        {columns.map((col) => (
          <nav key={col.title.en} aria-label={t(col.title)}>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-hl-amber">{t(col.title)}</p>
            <ul className="mt-3 space-y-2 text-sm">
              {col.links.map((link) => (
                <li key={link.to}>
                  <Link to={link.to} className="text-hl-cream/85 hover:text-white hover:underline">
                    {t(link.label)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <div className="border-t border-white/10">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-5 text-xs text-hl-cream/65 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="max-w-2xl">{t(FOOTER.fictional)}</p>
          <a href="/" className="inline-flex shrink-0 items-center gap-1 font-semibold text-hl-cream/85 hover:text-white hover:underline">
            {t(FOOTER.console)} <ArrowUpRight className="size-3.5" />
          </a>
        </div>
      </div>
    </footer>
  );
}
