import { Check, ChevronDown, X } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { type Bi, useT } from "@/portal/i18n";
import { FAQ, FOOTER, HELP, SITE } from "./content";
import { DemoForm, Field } from "./DemoForm";
import { PageHero } from "./PageHero";

export default function SiteHelp() {
  const t = useT();
  const jumps = [
    { hash: "#shipping", label: HELP.shipping.title },
    { hash: "#returns", label: HELP.returns.title },
    { hash: "#faq", label: FOOTER.faq },
    { hash: "#contact", label: FOOTER.contact },
  ];
  return (
    <>
      <PageHero eyebrow={t(HELP.eyebrow)} title={t(HELP.title)} lede={t(HELP.lede)}>
        <nav aria-label={t(HELP.jump)} className="mt-6 flex flex-wrap gap-2">
          {jumps.map((j) => (
            <Link
              key={j.hash}
              to={{ pathname: "/site/help", hash: j.hash }}
              className="rounded-full border border-hl-clay bg-white px-4 py-2 text-sm font-medium hover:bg-hl-sand"
            >
              {t(j.label)}
            </Link>
          ))}
        </nav>
      </PageHero>
      <div className="mx-auto flex max-w-6xl flex-col gap-16 px-4 sm:px-6">
        <Shipping />
        <Returns />
        <Faq />
        <Contact />
      </div>
    </>
  );
}

function Block({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24">
      <h2 id={`${id}-title`} className="font-display mb-5 text-3xl font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Panel({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-hl-clay bg-white">
      {title && <h3 className="px-5 pt-5 font-semibold">{title}</h3>}
      {children}
    </div>
  );
}

function List({ items, icon = "dot" }: { items: Bi[]; icon?: "dot" | "yes" | "no" }) {
  const t = useT();
  return (
    <ul className="space-y-2.5 p-5 pt-3 text-[0.95rem]">
      {items.map((item) => (
        <li key={item.en} className="flex gap-2.5">
          {icon === "yes" && <Check className="mt-0.5 size-4 shrink-0 text-hl-forest" />}
          {icon === "no" && <X className="mt-0.5 size-4 shrink-0 text-hl-rust" />}
          {icon === "dot" && <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-hl-amber" />}
          <span>{t(item)}</span>
        </li>
      ))}
    </ul>
  );
}

function Shipping() {
  const t = useT();
  const s = HELP.shipping;
  return (
    <Block id="shipping" title={t(s.title)}>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-2">
        <Panel>
          <div className="overflow-x-auto p-2">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">{t(s.zone)}</th>
                  <th scope="col">{t(s.carrier)}</th>
                  <th scope="col">{t(s.transit)}</th>
                </tr>
              </thead>
              <tbody>
                {s.zones.map((row) => (
                  <tr key={row.zone.en}>
                    <td className="font-medium">{t(row.zone)}</td>
                    <td>{row.carrier}</td>
                    <td className="whitespace-nowrap">{t(row.transit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title={t(s.costsTitle)}>
          <List items={s.costs} />
        </Panel>
        <Panel title={t(s.processingTitle)}>
          <div className="overflow-x-auto p-2">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">{t(s.order)}</th>
                  <th scope="col">{t(s.processing)}</th>
                </tr>
              </thead>
              <tbody>
                {s.processingRows.map((row) => (
                  <tr key={row.order.en}>
                    <td className="font-medium">{t(row.order)}</td>
                    <td>{t(row.time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="px-5 pb-5 text-sm text-hl-bark-muted">{t(s.cutoff)}</p>
        </Panel>
        <div className="space-y-5">
          <Panel title={t(HELP.changes.title)}>
            <p className="p-5 pt-3 text-[0.95rem]">{t(HELP.changes.body)}</p>
          </Panel>
          <div className="rounded-2xl bg-hl-sand p-5 text-[0.95rem]">{t(s.customs)}</div>
        </div>
      </div>
    </Block>
  );
}

function Returns() {
  const t = useT();
  const r = HELP.returns;
  return (
    <Block id="returns" title={t(r.title)}>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 md:grid-cols-2">
        <Panel title={t(r.yesTitle)}>
          <List items={r.yes} icon="yes" />
        </Panel>
        <Panel title={t(r.noTitle)}>
          <List items={r.no} icon="no" />
        </Panel>
        <Panel title={t(r.howTitle)}>
          <ol className="space-y-3 p-5 pt-3 text-[0.95rem]">
            {r.how.map((step, i) => (
              <li key={step.en} className="flex gap-3">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-hl-rust text-xs font-semibold text-white">{i + 1}</span>
                <span>{t(step)}</span>
              </li>
            ))}
          </ol>
        </Panel>
        <Panel title={t(HELP.damage.title)}>
          <List items={HELP.damage.items} />
        </Panel>
      </div>
    </Block>
  );
}

function Faq() {
  const t = useT();
  return (
    <Block id="faq" title={t(HELP.faq.title)}>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-2">
        {FAQ.map((group) => (
          <div key={group.group.en}>
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-hl-rust">{t(group.group)}</h3>
            <div className="divide-y divide-hl-clay overflow-hidden rounded-2xl border border-hl-clay bg-white">
              {group.items.map((item) => (
                <details key={item.q.en} className="group">
                  <summary className="flex items-start justify-between gap-4 px-5 py-4 font-medium hover:bg-hl-cream">
                    {t(item.q)}
                    <ChevronDown className="chevron mt-0.5 size-4 shrink-0 text-hl-bark-muted transition-transform" />
                  </summary>
                  <p className="px-5 pb-5 text-[0.95rem] leading-relaxed text-hl-bark-muted">{t(item.a)}</p>
                </details>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Block>
  );
}

function Contact() {
  const t = useT();
  const c = HELP.contact;
  return (
    <section id="contact" aria-labelledby="contact-title" className="scroll-mt-24 grid gap-8 rounded-3xl bg-hl-bark p-7 text-hl-cream sm:p-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div>
        <h2 id="contact-title" className="font-display text-3xl font-semibold">
          {t(c.title)}
        </h2>
        <p className="mt-3 text-hl-cream/85">{t(c.body)}</p>
        <p className="mt-5">
          <a href={`mailto:${SITE.support}`} className="font-semibold text-hl-amber hover:underline">
            {SITE.support}
          </a>
        </p>
      </div>
      <DemoForm submit={t(c.submit)} tone="dark">
        <div className="grid gap-4 text-hl-cream sm:grid-cols-2">
          <Field label={t(c.name)}>{(id) => <input id={id} required autoComplete="name" className="field" />}</Field>
          <Field label={t(c.email)}>
            {(id) => <input id={id} type="email" required autoComplete="email" className="field" />}
          </Field>
          <Field label={t(c.order)} className="sm:col-span-2">
            {(id) => <input id={id} className="field" />}
          </Field>
          <Field label={t(c.message)} className="sm:col-span-2">
            {(id) => <textarea id={id} required rows={4} className="field" />}
          </Field>
        </div>
      </DemoForm>
    </section>
  );
}
