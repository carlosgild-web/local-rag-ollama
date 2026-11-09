import { Check, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { type Lang, useLang, useT } from "@/portal/i18n";
import { BeadArt, CharmArt, FindingArt } from "./art";
import { type BeadProduct, CATALOG, type CharmProduct, FINISH, type Finding } from "./content";

export function price(value: number, lang: Lang): string {
  return new Intl.NumberFormat(lang === "es" ? "es-MX" : "en-US", { style: "currency", currency: "USD", currencyDisplay: "narrowSymbol" }).format(value);
}

function Card({ art, badge, children }: { art: ReactNode; badge?: string; children: ReactNode }) {
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-2xl border border-hl-clay bg-white">
      <div className="relative grid aspect-[4/3] place-items-center bg-gradient-to-b from-hl-cream to-hl-sand/70">
        {badge && (
          <span className="absolute left-3 top-3 rounded-full bg-hl-rust px-2.5 py-1 text-[0.7rem] font-semibold uppercase tracking-wider text-white">
            {badge}
          </span>
        )}
        {art}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-4">{children}</div>
    </article>
  );
}

function Price({ value }: { value: number }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <div className="mt-auto pt-3">
      <p className="text-lg font-semibold">
        {price(value, lang)} <span className="text-sm font-normal text-hl-bark-muted">USD {t(CATALOG.each)}</span>
      </p>
      <p className="text-xs text-hl-bark-muted">{t(CATALOG.trade)}</p>
    </div>
  );
}

export function BeadCard({ bead, badge }: { bead: BeadProduct; badge?: string }) {
  return (
    <Card art={<BeadArt shape={bead.shape} colors={bead.colors} className="w-3/5" />} badge={badge}>
      <p className="font-mono text-xs text-hl-bark-muted">{bead.sku}</p>
      <h3 className="font-semibold leading-snug">{bead.name}</h3>
      <p className="text-sm text-hl-bark-muted">{bead.size}</p>
      <Price value={bead.price} />
    </Card>
  );
}

export function CharmCard({ charm, badge }: { charm: CharmProduct; badge?: string }) {
  const t = useT();
  const finish = FINISH[charm.finish];
  return (
    <Card art={<CharmArt kind={charm.kind} finish={charm.finish} className="w-1/2" />} badge={badge}>
      <p className="font-mono text-xs text-hl-bark-muted">{charm.sku}</p>
      <h3 className="font-semibold leading-snug">{t(charm.name)}</h3>
      <p className="text-sm text-hl-bark-muted">{t(finish.label)}</p>
      <p
        className={cn(
          "mt-1 inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
          finish.nickelFree ? "bg-hl-forest-soft text-hl-forest" : "bg-hl-rust-soft text-hl-rust",
        )}
      >
        {finish.nickelFree ? <Check className="size-3" /> : <TriangleAlert className="size-3" />}
        {t(finish.nickel)}
      </p>
      <Price value={charm.price} />
    </Card>
  );
}

export function FindingCard({ finding }: { finding: Finding }) {
  const t = useT();
  return (
    <Card art={<FindingArt kind={finding.kind} className="w-1/2" />}>
      <h3 className="font-semibold leading-snug">{t(finding.name)}</h3>
      <p className="text-sm text-hl-bark-muted">{t(finding.detail)}</p>
      <p className="mt-auto pt-3 text-xs text-hl-bark-muted">{t(CATALOG.individually)}</p>
    </Card>
  );
}
