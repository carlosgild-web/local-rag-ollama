import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useT } from "@/portal/i18n";
import { BeadArt, CharmArt, CollectionStrand, FindingArt, HeroStrand } from "./art";
import { BEADS, CATALOG, CHARMS, COLLECTIONS, CRAFT, type Collection, HERO, SECTIONS, SITE, WHOLESALE } from "./content";
import { DemoForm, Field } from "./DemoForm";
import { photo } from "./photos";
import { BeadCard, CharmCard, Picture } from "./ProductCard";

export default function SiteHome() {
  return (
    <>
      <Hero />
      <div className="mx-auto flex max-w-6xl flex-col gap-20 px-4 pt-14 sm:px-6">
        <Collections />
        <ShopBy />
        <Favorites />
        <Story />
        <Trade />
        <Newsletter />
      </div>
    </>
  );
}

function Hero() {
  const t = useT();
  const hero = photo("hero-strand");
  return (
    <section className="relative overflow-hidden">
      <div className="mx-auto grid max-w-6xl items-center gap-6 px-4 pb-6 pt-10 sm:px-6 md:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] md:pt-14">
        <div className="hl-rise">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-hl-rust">{t(HERO.eyebrow)}</p>
          <h1 className="font-display mt-4 text-4xl leading-[1.05] font-semibold sm:text-6xl">{t(HERO.title)}</h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-hl-bark-muted sm:text-lg">{t(HERO.lede)}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/site/catalog"
              className="inline-flex items-center gap-2 rounded-full bg-hl-rust px-5 py-3 font-semibold text-white transition-opacity hover:opacity-90"
            >
              {t(HERO.shop)} <ArrowRight className="size-4" />
            </Link>
            <Link
              to="/site/wholesale"
              className="inline-flex items-center gap-2 rounded-full border border-hl-bark/25 px-5 py-3 font-semibold transition-colors hover:bg-hl-sand"
            >
              {t(HERO.trade)}
            </Link>
          </div>
        </div>
        {hero ? (
          <img
            src={hero}
            alt={t(HERO.photoAlt)}
            width={1200}
            height={900}
            fetchPriority="high"
            className="hl-rise mx-auto w-full max-w-[560px] rounded-3xl shadow-xl shadow-hl-bark/10"
          />
        ) : (
          <HeroStrand className="mx-auto w-full max-w-[520px]" />
        )}
      </div>
    </section>
  );
}

function SectionHead({ id, title, note, action }: { id?: string; title: string; note?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 id={id} className="font-display text-3xl font-semibold sm:text-4xl">
          {title}
        </h2>
        {note && <p className="mt-2 text-hl-bark-muted">{note}</p>}
      </div>
      {action}
    </div>
  );
}

function Collections() {
  const t = useT();
  return (
    <section aria-labelledby="collections">
      <SectionHead id="collections" title={t(SECTIONS.collections.title)} note={t(SECTIONS.collections.note)} />
      <div className="grid gap-5 md:grid-cols-2">
        {COLLECTIONS.map((c) => (
          <CollectionBanner key={c.id} collection={c} />
        ))}
      </div>
    </section>
  );
}

function CollectionBanner({ collection: c }: { collection: Collection }) {
  const t = useT();
  const scene = photo(`collection-${c.id}`);
  // On a photo, both banners use light text over a dark fade.
  const dark = c.id === "amber-hollow" || Boolean(scene);
  return (
    <article
      className={cn(
        "relative flex min-h-[340px] flex-col justify-between overflow-hidden rounded-3xl p-7",
        dark ? "bg-hl-forest text-hl-cream" : "bg-[#eef4f1] text-hl-bark",
      )}
    >
      {scene && (
        <>
          <img src={scene} alt={t(c.photoAlt)} loading="lazy" decoding="async" className="absolute inset-0 size-full object-cover" />
          <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-b from-[#1b140e]/85 via-[#1b140e]/45 to-[#1b140e]/10" />
        </>
      )}
      <div className="relative">
        <p className={cn("text-xs font-semibold uppercase tracking-[0.14em]", dark ? "text-hl-amber-light" : "text-hl-forest")}>
          {t(c.season)} · {t(c.status)}
        </p>
        <h3 className="font-display mt-2 text-3xl font-semibold sm:text-4xl">{c.name}</h3>
        <p className={cn("mt-3 max-w-sm", dark ? "text-hl-cream/85" : "text-hl-bark-muted")}>{t(c.body)}</p>
      </div>
      {!scene && (
        <CollectionStrand
          palette={c.palette}
          charms={c.charms}
          finish={dark ? "bronze" : "rhodium"}
          thread={dark ? "#d9cbb5" : "#a8957f"}
          className="mt-4 w-full max-w-[420px] self-end"
        />
      )}
      {c.id === "amber-hollow" && (
        <Link
          to="/site/catalog"
          className="relative mt-2 inline-flex w-fit items-center gap-2 rounded-full bg-hl-amber px-4 py-2 text-sm font-semibold text-hl-bark transition-opacity hover:opacity-90"
        >
          {t(SECTIONS.collections.cta)} <ArrowRight className="size-4" />
        </Link>
      )}
    </article>
  );
}

function ShopBy() {
  const t = useT();
  const tiles = [
    {
      to: "/site/catalog?c=beads",
      label: CATALOG.tabs.beads,
      photo: "GB-1014",
      art: <BeadArt shape="swirl" colors={BEADS[2].colors} className="size-24" />,
    },
    {
      to: "/site/catalog?c=charms",
      label: CATALOG.tabs.charms,
      photo: "CH-2004",
      art: <CharmArt kind="moon" finish="gold" className="size-24" />,
    },
    {
      to: "/site/catalog?c=findings",
      label: CATALOG.tabs.findings,
      photo: "finding-clasp",
      art: <FindingArt kind="clasp" className="size-24" />,
    },
    {
      to: "/site/wholesale#sets",
      label: WHOLESALE.sets.title,
      photo: "starter-set",
      art: <CollectionStrand palette={COLLECTIONS[0].palette} charms={["acorn"]} finish="bronze" className="h-24 w-auto" />,
    },
  ];
  return (
    <section>
      <SectionHead title={t(SECTIONS.shopBy.title)} />
      <ul className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {tiles.map((tile) => (
          <li key={tile.to}>
            <Link
              to={tile.to}
              className="group flex h-full flex-col items-center gap-3 overflow-hidden rounded-2xl border border-hl-clay bg-white pb-4 text-center transition-shadow hover:shadow-md"
            >
              <span className="relative grid aspect-[4/3] w-full place-items-center overflow-hidden bg-gradient-to-b from-hl-cream to-hl-sand/70">
                <Picture
                  name={tile.photo}
                  alt=""
                  fallback={<span className="transition-transform group-hover:-translate-y-1">{tile.art}</span>}
                  className="transition-transform duration-500 group-hover:scale-105"
                />
              </span>
              <span className="px-3 font-semibold">{t(tile.label)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Favorites() {
  const t = useT();
  const bead = (sku: string) => BEADS.find((b) => b.sku === sku)!;
  const charm = (sku: string) => CHARMS.find((c) => c.sku === sku)!;
  const best = t(SECTIONS.favorites.best);
  return (
    <section>
      <SectionHead
        title={t(SECTIONS.favorites.title)}
        action={
          <Link to="/site/catalog" className="inline-flex items-center gap-1.5 font-semibold text-hl-rust hover:underline">
            {t(SECTIONS.favorites.all)} <ArrowRight className="size-4" />
          </Link>
        }
      />
      <ul className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <li>
          <CharmCard charm={charm("CH-2004")} badge={best} />
        </li>
        <li>
          <BeadCard bead={bead("GB-1014")} badge={best} />
        </li>
        <li>
          <BeadCard bead={bead("GB-1033")} />
        </li>
        <li>
          <CharmCard charm={charm("CH-2019")} />
        </li>
      </ul>
    </section>
  );
}

function Story() {
  const t = useT();
  const workshop = photo("story-workshop");
  return (
    <section id="story" className="scroll-mt-24 rounded-3xl bg-hl-sand p-7 sm:p-10">
      {workshop && (
        <img
          src={workshop}
          alt={t(SECTIONS.story.photoAlt)}
          loading="lazy"
          decoding="async"
          className="mb-8 aspect-[21/9] w-full rounded-2xl object-cover"
        />
      )}
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-hl-rust">{t(SECTIONS.story.eyebrow)}</p>
          <h2 className="font-display mt-3 text-3xl font-semibold sm:text-4xl">{t(SECTIONS.story.title)}</h2>
          <p className="mt-4 leading-relaxed text-hl-bark-muted">{t(SECTIONS.story.body)}</p>
          <p className="mt-6 text-sm font-semibold">
            {SITE.address} · {SITE.city} · {t({ es: "Desde", en: "Since" })} {SITE.founded}
          </p>
        </div>
        <ul className="grid gap-4 sm:grid-cols-3 lg:grid-cols-1">
          {CRAFT.map((item, i) => (
            <li key={item.title.en} className="flex gap-4 rounded-2xl bg-hl-cream p-5">
              <span className="font-display text-2xl font-semibold text-hl-rust" aria-hidden="true">
                0{i + 1}
              </span>
              <div>
                <h3 className="font-semibold">{t(item.title)}</h3>
                <p className="mt-1 text-sm leading-relaxed text-hl-bark-muted">{t(item.body)}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Trade() {
  const t = useT();
  return (
    <section className="relative overflow-hidden rounded-3xl bg-hl-bark p-7 text-hl-cream sm:p-10">
      <div className="relative z-10 max-w-xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-hl-amber">{t(SECTIONS.trade.eyebrow)}</p>
        <h2 className="font-display mt-3 text-3xl font-semibold sm:text-4xl">{t(SECTIONS.trade.title)}</h2>
        <p className="mt-3 text-hl-cream/85">{t(SECTIONS.trade.body)}</p>
        <Link
          to="/site/wholesale"
          className="mt-6 inline-flex items-center gap-2 rounded-full bg-hl-amber px-5 py-3 font-semibold text-hl-bark transition-opacity hover:opacity-90"
        >
          {t(SECTIONS.trade.cta)} <ArrowRight className="size-4" />
        </Link>
      </div>
      <CollectionStrand
        palette={["#e39a2d", "#eadfe8", "#5fae9c", "#2f45b5", "#c87f3a"]}
        charms={["moon", "leaf"]}
        finish="gold"
        thread="#d9cbb5"
        className="pointer-events-none absolute -bottom-6 -right-10 hidden w-[420px] opacity-90 md:block"
      />
    </section>
  );
}

function Newsletter() {
  const t = useT();
  return (
    <section className="grid items-center gap-6 rounded-3xl border border-hl-clay bg-white p-7 sm:p-10 md:grid-cols-2">
      <div>
        <h2 className="font-display text-3xl font-semibold">{t(SECTIONS.newsletter.title)}</h2>
        <p className="mt-2 text-hl-bark-muted">{t(SECTIONS.newsletter.body)}</p>
      </div>
      <DemoForm submit={t(SECTIONS.newsletter.submit)}>
        <Field label={t(SECTIONS.newsletter.email)}>
          {(id) => <input id={id} type="email" required autoComplete="email" className="field" placeholder="you@example.com" />}
        </Field>
      </DemoForm>
    </section>
  );
}
