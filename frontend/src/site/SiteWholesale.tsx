import { Check, Mail } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLang, useT } from "@/portal/i18n";
import { CollectionStrand } from "./art";
import { SITE, STARTER_SETS, TIERS, WHOLESALE } from "./content";
import { DemoForm, Field } from "./DemoForm";
import { PageHero } from "./PageHero";
import { price } from "./ProductCard";

export default function SiteWholesale() {
  const t = useT();
  return (
    <>
      <PageHero eyebrow={t(WHOLESALE.eyebrow)} title={t(WHOLESALE.title)} lede={t(WHOLESALE.lede)} />
      <div className="mx-auto flex max-w-6xl flex-col gap-16 px-4 sm:px-6">
        <Tiers />
        <Steps />
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <Sets />
          <Custom />
        </div>
        <Terms />
        <Application />
      </div>
    </>
  );
}

function Tiers() {
  const t = useT();
  return (
    <section aria-labelledby="tiers">
      <h2 id="tiers" className="font-display mb-6 text-3xl font-semibold">
        {t(WHOLESALE.tiersTitle)}
      </h2>
      <ul className="grid gap-4 md:grid-cols-3">
        {TIERS.map((tier) => (
          <li
            key={tier.name.en}
            className={cn(
              "flex flex-col rounded-2xl border p-6",
              tier.featured ? "border-hl-bark bg-hl-bark text-hl-cream" : "border-hl-clay bg-white",
            )}
          >
            <h3 className="font-semibold">{t(tier.name)}</h3>
            <p className="font-display mt-4 text-5xl font-semibold">{tier.discount}</p>
            <p className={cn("text-sm", tier.featured ? "text-hl-cream/75" : "text-hl-bark-muted")}>{t(WHOLESALE.off)}</p>
            <ul className={cn("mt-5 space-y-2 text-sm", tier.featured ? "text-hl-cream/90" : "text-hl-bark")}>
              {[tier.minimum, tier.terms, tier.note].filter(Boolean).map((line) => (
                <li key={line!.en} className="flex gap-2">
                  <Check className={cn("mt-0.5 size-4 shrink-0", tier.featured ? "text-hl-amber" : "text-hl-forest")} />
                  {t(line!)}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Steps() {
  const t = useT();
  return (
    <section aria-labelledby="steps" className="rounded-3xl bg-hl-sand p-7 sm:p-10">
      <h2 id="steps" className="font-display text-3xl font-semibold">
        {t(WHOLESALE.steps.title)}
      </h2>
      <ol className="mt-6 grid gap-4 md:grid-cols-3">
        {WHOLESALE.steps.items.map((step, i) => (
          <li key={step.title.en} className="rounded-2xl bg-hl-cream p-5">
            <span className="grid size-9 place-items-center rounded-full bg-hl-rust font-semibold text-white">{i + 1}</span>
            <h3 className="mt-3 font-semibold">{t(step.title)}</h3>
            <p className="mt-1 text-sm text-hl-bark-muted">{t(step.body)}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Sets() {
  const t = useT();
  const { lang } = useLang();
  return (
    <section id="sets" aria-labelledby="sets-title" className="scroll-mt-24 rounded-2xl border border-hl-clay bg-white">
      <div className="px-5 pt-5">
        <h2 id="sets-title" className="font-display text-2xl font-semibold">
          {t(WHOLESALE.sets.title)}
        </h2>
        <p className="mt-1 text-sm text-hl-bark-muted">{t(WHOLESALE.sets.note)}</p>
      </div>
      <div className="overflow-x-auto p-2">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">{t(WHOLESALE.sets.set)}</th>
              <th scope="col" className="text-right">
                {t(WHOLESALE.sets.boutique)}
              </th>
              <th scope="col" className="text-right">
                {t(WHOLESALE.sets.large)}
              </th>
            </tr>
          </thead>
          <tbody>
            {STARTER_SETS.map((set) => (
              <tr key={set.name.en}>
                <td>
                  <p className="font-medium">{t(set.name)}</p>
                  <p className="text-sm text-hl-bark-muted">{t(set.contents)}</p>
                </td>
                <td className="text-right font-medium tabular-nums">{price(set.boutique, lang)}</td>
                <td className="text-right font-medium tabular-nums">{price(set.large, lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Custom() {
  const t = useT();
  return (
    <section aria-labelledby="custom" className="relative flex flex-col overflow-hidden rounded-2xl bg-hl-forest p-6 text-hl-cream">
      <h2 id="custom" className="font-display text-2xl font-semibold">
        {t(WHOLESALE.custom.title)}
      </h2>
      <p className="mt-3 text-hl-cream/85">{t(WHOLESALE.custom.body)}</p>
      <p className="mt-3 text-sm text-hl-cream/75">{t(WHOLESALE.custom.final)}</p>
      <p className="mt-5 text-sm">
        {t(WHOLESALE.custom.ask)}{" "}
        <a href={`mailto:${SITE.wholesale}`} className="inline-flex items-center gap-1 font-semibold text-hl-amber-light hover:underline">
          <Mail className="size-4" /> {SITE.wholesale}
        </a>
      </p>
      <CollectionStrand
        palette={["#2f45b5", "#5fae9c", "#e7a3a6", "#e39a2d", "#eadfe8"]}
        charms={[]}
        finish="gold"
        thread="#d9cbb5"
        className="mt-auto w-full max-w-[320px] self-end pt-4 opacity-90"
      />
    </section>
  );
}

function Terms() {
  const t = useT();
  return (
    <section aria-labelledby="terms">
      <h2 id="terms" className="font-display text-2xl font-semibold">
        {t(WHOLESALE.terms.title)}
      </h2>
      <ul className="mt-4 grid gap-3 md:grid-cols-3">
        {WHOLESALE.terms.items.map((item) => (
          <li key={item.en} className="flex gap-2 rounded-xl border border-hl-clay bg-white p-4 text-sm">
            <Check className="mt-0.5 size-4 shrink-0 text-hl-forest" /> {t(item)}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Application() {
  const t = useT();
  const f = WHOLESALE.form;
  return (
    <section id="apply" aria-labelledby="apply-title" className="scroll-mt-24 rounded-3xl border border-hl-clay bg-white p-7 sm:p-10">
      <h2 id="apply-title" className="font-display text-3xl font-semibold">
        {t(f.title)}
      </h2>
      <DemoForm submit={t(f.submit)} className="mt-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t(f.business)}>{(id) => <input id={id} required autoComplete="organization" className="field" />}</Field>
          <Field label={t(f.contact)}>
            {(id) => <input id={id} type="email" required autoComplete="email" className="field" />}
          </Field>
          <Field label={t(f.country)}>{(id) => <input id={id} required autoComplete="country-name" className="field" />}</Field>
          <Field label={t(f.tier)}>
            {(id) => (
              <select id={id} className="field" defaultValue="boutique">
                {TIERS.slice(0, 2).map((tier, i) => (
                  <option key={tier.name.en} value={i === 0 ? "boutique" : "large"}>
                    {t(tier.name)} · {t(tier.minimum)}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label={t(f.license)} className="sm:col-span-2">
            {(id) => <input id={id} required className="field" />}
          </Field>
          <Field label={t(f.message)} className="sm:col-span-2">
            {(id) => <textarea id={id} rows={4} className="field" />}
          </Field>
        </div>
      </DemoForm>
    </section>
  );
}
