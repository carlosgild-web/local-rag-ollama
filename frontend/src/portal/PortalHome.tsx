import { ArrowRight, FileText, MessageCircle, Search } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { COMPANY, HANDBOOK, HERO, HOURS, NEWS, SEASON, SECTIONS, type SeasonItem } from "./content";
import { type Bi, type Lang, UI, useLang, useT } from "./i18n";
import { BEAD, Bead } from "./Logo";
import { documentTitle, useLuna } from "./luna";

export default function PortalHome() {
  return (
    <>
      <Hero />
      <div className="mx-auto flex max-w-6xl flex-col gap-16 px-4 pt-12 sm:px-6">
        <Season />
        <Handbook />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <Hours />
          <Company />
        </div>
        <News />
      </div>
    </>
  );
}

/** Asks Luna in the floating panel, so the page stays where it is. */
function useAskInBubble() {
  const luna = useLuna();
  return (question: string) => {
    luna.ask(question);
    luna.setBubbleOpen(true);
  };
}

function greeting(): keyof typeof HERO.greeting {
  const hour = new Date().getHours();
  return hour < 12 ? "morning" : hour < 19 ? "afternoon" : "evening";
}

function Hero() {
  const t = useT();
  const { lang } = useLang();
  const luna = useLuna();
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  // "domingo, 8 de noviembre" → "Domingo, 8 de noviembre" (sentence case, right in both languages).
  const date = new Intl.DateTimeFormat(locale(lang), { weekday: "long", day: "numeric", month: "long" }).format(
    new Date(),
  );
  const today = date.charAt(0).toUpperCase() + date.slice(1);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!question.trim()) return;
    luna.ask(question);
    navigate("/intranet/luna");
  };

  return (
    <section className="relative overflow-hidden bg-hl-night text-hl-moon">
      <Strand />
      <div className="relative mx-auto max-w-6xl px-4 pb-14 pt-10 sm:px-6 sm:pb-20 sm:pt-14">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-hl-amber">{t(HERO.eyebrow)}</p>
        <p className="mt-4 text-sm text-hl-moon/70">
          {t(HERO.greeting[greeting()])} · {today}
        </p>
        <h1 className="font-display mt-2 max-w-2xl text-4xl leading-[1.05] font-semibold sm:text-6xl">
          {t(HERO.title)}
        </h1>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-hl-moon/80 sm:text-lg">{t(HERO.lede)}</p>

        <form onSubmit={submit} className="mt-8 max-w-2xl">
          <label htmlFor="hero-ask" className="sr-only">
            {t(UI.nav.luna)}
          </label>
          <div className="flex items-center gap-2 rounded-2xl bg-white p-2 text-hl-ink shadow-2xl ring-1 ring-black/5">
            <Search className="ml-2 size-5 shrink-0 text-hl-muted" />
            <input
              id="hero-ask"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={t(UI.luna.heroPlaceholder)}
              maxLength={4000}
              className="min-w-0 flex-1 bg-transparent px-1 py-2.5 text-base outline-none placeholder:text-hl-muted"
            />
            <button
              type="submit"
              disabled={!question.trim()}
              className="flex shrink-0 items-center gap-2 rounded-xl bg-hl-amber px-4 py-2.5 font-semibold text-hl-night transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              <span className="max-sm:sr-only">{t(UI.nav.luna)}</span>
              <ArrowRight className="size-4" />
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}

/** A necklace of glass beads draped across the hero, with a star charm at its lowest point. */
function Strand() {
  const colors = [BEAD.cobalt, BEAD.amber, BEAD.sea, BEAD.opal, BEAD.cobalt, BEAD.moonstone];
  const count = 23;
  const beads = Array.from({ length: count }, (_, i) => {
    const t = i / (count - 1);
    const x = 40 + t * 720;
    const y = 30 + 210 * (1 - (2 * t - 1) ** 2);
    const r = 9 + 7 * Math.sin(Math.PI * t) + (i % 3 === 0 ? 3 : 0);
    return { x, y, r, fill: colors[i % colors.length] };
  });
  const thread = `M${beads[0].x} ${beads[0].y} Q 400 450 ${beads[count - 1].x} ${beads[count - 1].y}`;
  const low = beads[Math.floor(count / 2)];
  return (
    <svg
      viewBox="0 0 800 320"
      aria-hidden="true"
      className="pointer-events-none absolute top-6 hidden w-[880px] max-w-none sm:-right-24 sm:block sm:opacity-50 lg:right-[-60px] lg:opacity-90"
    >
      <path d={thread} fill="none" stroke="#eef0f8" strokeWidth={1.4} opacity={0.35} />
      {beads.map((b, i) => (
        <g key={b.x} className="hl-bead" style={{ animationDelay: `${i * 35}ms` }}>
          <Bead {...b} />
        </g>
      ))}
      <line x1={low.x} y1={low.y + low.r} x2={low.x} y2={low.y + low.r + 22} stroke="#eef0f8" strokeWidth={1.2} opacity={0.5} />
      <path
        className="hl-bead"
        style={{ animationDelay: `${count * 35}ms` }}
        d={star(low.x, low.y + low.r + 40, 18)}
        fill={BEAD.amber}
      />
    </svg>
  );
}

function star(x: number, y: number, size: number): string {
  return (
    Array.from({ length: 10 }, (_, k) => {
      const r = k % 2 ? size * 0.45 : size;
      const a = -Math.PI / 2 + (k * Math.PI) / 5;
      return `${k ? "L" : "M"}${(x + r * Math.cos(a)).toFixed(1)} ${(y + r * Math.sin(a)).toFixed(1)}`;
    }).join("") + "Z"
  );
}

function SectionHead({ id, title, note }: { id: string; title: Bi; note?: Bi }) {
  const t = useT();
  return (
    <div className="mb-6 flex flex-col gap-1">
      <h2 id={id} className="font-display scroll-mt-24 text-3xl font-semibold">
        {t(title)}
      </h2>
      {note && <p className="text-sm text-hl-muted">{t(note)}</p>}
    </div>
  );
}

// --- This season ---------------------------------------------------------------

function locale(lang: Lang) {
  return lang === "es" ? "es-MX" : "en-US";
}

function day(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function dateLabel(item: SeasonItem, lang: Lang): string {
  const format = new Intl.DateTimeFormat(locale(lang), { day: "numeric", month: "short" });
  return item.end ? format.formatRange(day(item.start), day(item.end)) : format.format(day(item.start));
}

type Phase = "done" | "now" | "next";

function phase(item: SeasonItem, today: Date): Phase {
  const start = day(item.start);
  const end = day(item.end ?? item.start);
  if (end < today) return "done";
  if (start <= today) return "now";
  return "next";
}

function Season() {
  const t = useT();
  const { lang } = useLang();
  const ask = useAskInBubble();
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const firstUpcoming = SEASON.findIndex((item) => phase(item, today) === "next");

  return (
    <section aria-labelledby="season">
      <SectionHead id="season" title={SECTIONS.season.title} note={SECTIONS.season.note} />
      <ol className="grid gap-3 md:grid-cols-5">
        {SEASON.map((item, i) => {
          const p = phase(item, today);
          return (
            <li
              key={item.start}
              className={cn(
                "relative flex flex-col gap-2 rounded-2xl bg-hl-card p-4 ring-1 ring-hl-line",
                p === "now" && "ring-2 ring-hl-amber",
                p === "done" && "opacity-60",
              )}
            >
              <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                <span className="text-sm font-semibold tabular-nums text-hl-cobalt">{dateLabel(item, lang)}</span>
                {p === "now" && (
                  <span className="whitespace-nowrap rounded-full bg-hl-amber px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-hl-night">
                    {t(SECTIONS.season.now)}
                  </span>
                )}
                {p === "done" && (
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-hl-muted">
                    {t(SECTIONS.season.done)}
                  </span>
                )}
                {i === firstUpcoming && p === "next" && (
                  <span className="whitespace-nowrap text-[11px] font-semibold uppercase tracking-wider text-hl-amber-ink">
                    {daysUntil(item, today, lang)}
                  </span>
                )}
              </div>
              <h3 className="font-semibold leading-snug">{t(item.title)}</h3>
              <p className="flex-1 text-sm leading-relaxed text-hl-muted">{t(item.detail)}</p>
              <AskLink onClick={() => ask(t(item.ask))} />
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function daysUntil(item: SeasonItem, today: Date, lang: Lang): string {
  const days = Math.round((day(item.start).getTime() - today.getTime()) / 86_400_000);
  return new Intl.RelativeTimeFormat(locale(lang), { numeric: "auto" }).format(days, "day");
}

function AskLink({ onClick, label }: { onClick: () => void; label?: string }) {
  const t = useT();
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 self-start rounded-md text-sm font-semibold text-hl-cobalt hover:underline"
    >
      <MessageCircle className="size-4" /> {label ?? t(SECTIONS.ask)}
    </button>
  );
}

// --- Handbook, hours, company, news ------------------------------------------

function Handbook() {
  const t = useT();
  const ask = useAskInBubble();
  return (
    <section aria-labelledby="handbook">
      <SectionHead id="handbook" title={SECTIONS.handbook.title} note={SECTIONS.handbook.note} />
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {HANDBOOK.map((topic) => (
          <li key={topic.title.en}>
            <button
              type="button"
              onClick={() => ask(t(topic.ask))}
              className="group flex h-full w-full flex-col gap-2 rounded-2xl bg-hl-card p-5 text-left ring-1 ring-hl-line transition-shadow hover:shadow-lg hover:ring-hl-cobalt/40"
            >
              <span className="font-display text-2xl font-semibold text-hl-cobalt">{t(topic.figure)}</span>
              <span className="font-semibold">{t(topic.title)}</span>
              <span className="flex-1 text-sm leading-relaxed text-hl-muted">{t(topic.detail)}</span>
              <span className="mt-1 inline-flex items-center gap-1.5 text-sm font-semibold text-hl-cobalt">
                <MessageCircle className="size-4" /> <span className="group-hover:underline">{t(topic.ask)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Hours() {
  const t = useT();
  return (
    <section aria-labelledby="hours">
      <SectionHead id="hours" title={SECTIONS.hours.title} />
      <div className="overflow-x-auto rounded-2xl bg-hl-card ring-1 ring-hl-line">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.1em] text-hl-muted">
            <tr className="border-b border-hl-line">
              <th className="px-5 py-3 font-semibold">{t(SECTIONS.hours.department)}</th>
              <th className="px-5 py-3 font-semibold">{t(SECTIONS.hours.hours)}</th>
              <th className="px-5 py-3 font-semibold">{t(SECTIONS.hours.note)}</th>
            </tr>
          </thead>
          <tbody>
            {HOURS.map((row) => (
              <tr key={row.department.en} className="border-b border-hl-line last:border-0">
                <td className="px-5 py-3 font-semibold">{t(row.department)}</td>
                <td className="px-5 py-3 tabular-nums">{t(row.hours)}</td>
                <td className="px-5 py-3 text-hl-muted">{t(row.note)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Company() {
  const t = useT();
  const rows: [Bi, string][] = [
    [SECTIONS.company.founded, String(COMPANY.founded)],
    [SECTIONS.company.people, COMPANY.employees],
    [SECTIONS.company.hq, `${COMPANY.city} · ${COMPANY.address}`],
    [SECTIONS.company.hr, COMPANY.hrEmail],
  ];
  return (
    <section aria-labelledby="company">
      <SectionHead id="company" title={SECTIONS.company.title} />
      <div className="rounded-2xl bg-hl-night p-6 text-hl-moon">
        <p className="leading-relaxed text-hl-moon/85">{t(SECTIONS.company.what)}</p>
        <dl className="mt-5 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-sm">
          {rows.map(([label, value]) => (
            <div key={label.en} className="contents">
              <dt className="text-hl-moon/60">{t(label)}</dt>
              <dd className="select-all break-words font-semibold">{value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function News() {
  const t = useT();
  const ask = useAskInBubble();
  return (
    <section aria-labelledby="news">
      <SectionHead id="news" title={SECTIONS.news.title} note={SECTIONS.news.note} />
      <ul className="grid gap-4 md:grid-cols-3">
        {NEWS.map((item) => (
          <li key={item.title.en} className="flex flex-col gap-3 rounded-2xl bg-hl-card p-5 ring-1 ring-hl-line">
            <span className="text-xs font-bold uppercase tracking-[0.14em] text-hl-amber-ink">{t(item.kicker)}</span>
            <h3 className="font-display text-xl font-semibold leading-snug">{t(item.title)}</h3>
            <p className="flex-1 text-sm leading-relaxed text-hl-muted">{t(item.body)}</p>
            <p className="flex items-center gap-1.5 text-xs text-hl-muted">
              <FileText className="size-3.5" /> {documentTitle(item.source)}
            </p>
            <AskLink onClick={() => ask(t(item.ask))} />
          </li>
        ))}
      </ul>
    </section>
  );
}
