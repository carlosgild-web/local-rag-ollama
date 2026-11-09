import { ArrowLeft, ArrowRight, Info } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useT } from "@/portal/i18n";
import { LogoMark } from "@/portal/Logo";
import { STAFF } from "./content";

/**
 * The door from the public site to the intranet. It is a simulation and says
 * so: there are no accounts, nothing is checked, and /intranet stays open to
 * anyone who can reach the server (decisions 0010 and 0011).
 */
export default function StaffSignIn() {
  const t = useT();
  const navigate = useNavigate();
  return (
    <section className="mx-auto grid max-w-6xl place-items-center px-4 py-14 sm:px-6 sm:py-20">
      <div className="hl-rise w-full max-w-md overflow-hidden rounded-3xl border border-hl-clay bg-white shadow-xl shadow-hl-bark/5">
        <div className="relative bg-hl-night px-7 pb-8 pt-7 text-hl-moon">
          <LogoMark className="size-16 text-hl-moon" />
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.16em] text-hl-amber">{t(STAFF.eyebrow)}</p>
          <h1 className="font-display mt-1 text-3xl font-semibold">{t(STAFF.title)}</h1>
          <p className="mt-2 text-sm text-hl-moon/80">{t(STAFF.body)}</p>
        </div>
        <div className="space-y-5 p-7">
          <div role="note" className="flex gap-3 rounded-2xl bg-hl-rust-soft p-4 text-sm">
            <Info className="mt-0.5 size-4 shrink-0 text-hl-rust" />
            <div>
              <p className="font-semibold text-hl-rust">{t(STAFF.simulated)}</p>
              <p className="mt-1 text-hl-bark">{t(STAFF.simulatedBody)}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => navigate("/intranet")}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-hl-night px-5 py-3 font-semibold text-white transition-opacity hover:opacity-90"
          >
            {t(STAFF.enter)} <ArrowRight className="size-4" />
          </button>
          <Link to="/site" className="flex items-center justify-center gap-1.5 text-sm font-medium text-hl-bark-muted hover:text-hl-bark">
            <ArrowLeft className="size-4" /> {t(STAFF.back)}
          </Link>
        </div>
      </div>
    </section>
  );
}
