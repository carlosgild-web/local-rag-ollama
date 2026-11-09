import { useSearchParams } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useT } from "@/portal/i18n";
import { BEADS, CATALOG, type Category, CHARMS, FINDINGS } from "./content";
import { PageHero } from "./PageHero";
import { BeadCard, CharmCard, FindingCard } from "./ProductCard";

const ORDER: Category[] = ["beads", "charms", "findings"];

export default function SiteCatalog() {
  const t = useT();
  const [params, setParams] = useSearchParams();
  const requested = params.get("c");
  const tab: Category = ORDER.includes(requested as Category) ? (requested as Category) : "beads";

  return (
    <>
      <PageHero eyebrow={t(CATALOG.eyebrow)} title={t(CATALOG.title)} lede={t(CATALOG.lede)} />
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div role="tablist" aria-label={t(CATALOG.title)} className="flex gap-2 overflow-x-auto pb-1">
          {ORDER.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              id={`tab-${key}`}
              aria-selected={tab === key}
              aria-controls="catalog-panel"
              onClick={() => setParams(key === "beads" ? {} : { c: key }, { replace: true })}
              className={cn(
                "shrink-0 rounded-full border px-4 py-2 font-medium transition-colors",
                tab === key ? "border-hl-bark bg-hl-bark text-hl-cream" : "border-hl-clay bg-white hover:bg-hl-sand",
              )}
            >
              {t(CATALOG.tabs[key])}
            </button>
          ))}
        </div>

        <div id="catalog-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="mt-6">
          <p className="mb-5 max-w-2xl text-hl-bark-muted">{t(CATALOG.tabNotes[tab])}</p>
          <ul className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
            {tab === "beads" &&
              BEADS.map((bead) => (
                <li key={bead.sku}>
                  <BeadCard bead={bead} />
                </li>
              ))}
            {tab === "charms" &&
              CHARMS.map((charm) => (
                <li key={charm.sku}>
                  <CharmCard charm={charm} />
                </li>
              ))}
            {tab === "findings" &&
              FINDINGS.map((finding) => (
                <li key={finding.kind}>
                  <FindingCard finding={finding} />
                </li>
              ))}
          </ul>
        </div>

        <section className="mt-14 rounded-2xl border border-hl-clay bg-white">
          <h2 className="font-display px-5 pt-5 text-2xl font-semibold">{t(CATALOG.tiers.title)}</h2>
          <div className="overflow-x-auto p-2">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">{t(CATALOG.tiers.who)}</th>
                  <th scope="col">{t(CATALOG.tiers.min)}</th>
                  <th scope="col">{t(CATALOG.tiers.ships)}</th>
                </tr>
              </thead>
              <tbody>
                {CATALOG.tiers.rows.map((row) => (
                  <tr key={row.who.en}>
                    <td className="font-medium">{t(row.who)}</td>
                    <td>{t(row.min)}</td>
                    <td>{t(row.ships)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
}
