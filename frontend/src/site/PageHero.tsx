import type { ReactNode } from "react";

/** The title band at the top of the catalog, wholesale and help pages. */
export function PageHero({ eyebrow, title, lede, children }: { eyebrow: string; title: string; lede: string; children?: ReactNode }) {
  return (
    <section className="mx-auto max-w-6xl px-4 pb-8 pt-10 sm:px-6 sm:pt-14">
      <div className="hl-rise max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-hl-rust">{eyebrow}</p>
        <h1 className="font-display mt-3 text-4xl leading-[1.08] font-semibold sm:text-5xl">{title}</h1>
        <p className="mt-4 text-base leading-relaxed text-hl-bark-muted sm:text-lg">{lede}</p>
        {children}
      </div>
    </section>
  );
}
