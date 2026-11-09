/**
 * The reviewer's guide through the demo (decision 0011). It is deliberately
 * NOT part of the fictional company's design: neutral charcoal, a dashed edge,
 * a monospace "portfolio demo" tag, and the console's plain sans font, so
 * nobody mistakes it for Hilda & Luna's branding.
 *
 * - On the public site: a one-line strip pointing to Employee login.
 * - On the intranet: a banner with "How this demo works" (a side panel) and
 *   the way into the RAG admin console.
 * - Closed, both collapse to a small "Demo guide" pill (bottom left, away from
 *   Luna's bubble), remembered in this browser for both sites.
 */
import { ArrowRight, ArrowUpRight, BookOpen, Compass, X } from "lucide-react";
import { useCallback, useState, useSyncExternalStore } from "react";
import { Link, useLocation } from "react-router-dom";
import { Dialog } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { type Bi, useT } from "./i18n";

const KEY = "hl-demo-guide";
const REPO = "https://github.com/carlosgild-web/local-rag-ollama#readme";

type Mode = "open" | "pill";
const listeners = new Set<() => void>();
let memory: Mode | null = null;

function readMode(): Mode {
  try {
    return localStorage.getItem(KEY) === "pill" ? "pill" : "open";
  } catch {
    return "open"; // storage blocked: the guide simply shows
  }
}

function writeMode(mode: Mode) {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    // not remembered; still changes for this visit
  }
  memory = mode;
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  const onStorage = (e: StorageEvent) => e.key === KEY && ((memory = null), fn());
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(fn);
    window.removeEventListener("storage", onStorage);
  };
}

/** Banner or pill, shared by every guide on the page and both sites. */
export function useDemoGuide(): [Mode, (mode: Mode) => void] {
  const mode = useSyncExternalStore(subscribe, () => memory ?? (memory = readMode()));
  return [mode, writeMode];
}

const GUIDE = {
  tag: { es: "Demo de portafolio · no es parte del diseño de la empresa", en: "Portfolio demo · not part of the company design" },
  strip: {
    es: "Empresa ficticia para demostrar un sistema RAG local. Empieza aquí:",
    en: "A fictional company, made to demo a local RAG system. Start here:",
  },
  path: { es: "Acceso empleados → intranet → consola RAG", en: "Employee login → intranet → RAG console" },
  banner: {
    es: "Estás en la intranet de una empresa ficticia, creada para demostrar un sistema RAG local. Luna responde solo con los documentos que se administran en la consola.",
    en: "You're inside a fictional company's intranet, made to demo a local RAG system. Luna answers only from the documents managed in the admin console.",
  },
  how: { es: "Cómo funciona esta demo", en: "How this demo works" },
  console: { es: "Abrir la consola RAG", en: "Open the RAG admin console" },
  hide: { es: "Ocultar la guía", en: "Hide the guide" },
  pill: { es: "Guía de la demo", en: "Demo guide" },
  close: { es: "Cerrar", en: "Close" },
  panel: {
    lede: {
      es: "Para quien revisa el proyecto. La empresa, su gente y sus 11 documentos son ficticios.",
      en: "For anyone reviewing the project. The company, its people and its 11 documents are fictional.",
    },
    whatTitle: { es: "Qué es", en: "What this is" },
    what: {
      es: "Una aplicación RAG (generación aumentada por recuperación) que corre por completo en esta computadora. Ollama ejecuta los modelos de chat y de embeddings; FastAPI, SQLite con FTS5 y Chroma guardan y buscan los documentos; React dibuja las tres caras que ves. Nada se envía a la nube.",
      en: "A retrieval-augmented generation (RAG) app that runs entirely on this computer. Ollama runs the chat and embedding models; FastAPI, SQLite with FTS5 and Chroma store and search the documents; React draws the three faces you see. Nothing is sent to the cloud.",
    },
    pathTitle: { es: "El recorrido", en: "The path" },
    here: { es: "Estás aquí", en: "You are here" },
    steps: [
      {
        title: { es: "Sitio público", en: "Public website" },
        body: { es: "La cara externa de la empresa, escrita con sus documentos para clientes.", en: "The company's outside face, written from its customer documents." },
      },
      {
        title: { es: "Acceso empleados → intranet", en: "Employee login → intranet" },
        body: { es: "Un acceso simulado: sin cuentas, un solo botón.", en: "A simulated sign-in: no accounts, one button." },
      },
      {
        title: { es: "Pregúntale a Luna", en: "Ask Luna" },
        body: {
          es: "Luna responde solo con los documentos indexados, con citas numeradas y el fragmento exacto.",
          en: "Luna answers only from the indexed documents, with numbered citations and the exact passage.",
        },
      },
      {
        title: { es: "Consola de administración RAG", en: "RAG admin console" },
        body: {
          es: "Donde se suben, versionan e indexan los documentos: estantes, versiones automáticas, la papelera, la cola de trabajos y el diagnóstico.",
          en: "Where documents are uploaded, versioned and indexed: shelves, automatic versions, the trash, the job queue and the troubleshooter.",
        },
      },
    ] as { title: Bi; body: Bi }[],
    tryTitle: { es: "Prueba esto", en: "Things to try" },
    tries: [
      {
        es: "Pregúntale a Luna «¿Cuándo cierra la empresa por las fiestas?» y abre una de sus fuentes.",
        en: "Ask Luna “When does the company close for the holidays?” and open one of its sources.",
      },
      {
        es: "Pregunta algo que los documentos no dicen: Luna lo reconoce en vez de inventar.",
        en: "Ask something the documents don't cover: Luna says so instead of guessing.",
      },
      {
        es: "En la consola, sube una versión modificada de un documento con el mismo nombre: se vuelve la versión 2. Luego pregúntale de nuevo a Luna.",
        en: "In the console, upload a changed copy of a document under the same name: it becomes version 2. Then ask Luna again.",
      },
      {
        es: "Apaga el interruptor «Visible in the employee portal» de un estante y mira cómo Luna deja de usarlo.",
        en: "Turn off a shelf's “Visible in the employee portal” switch and watch Luna stop using it.",
      },
      {
        es: "En el tablero de la consola, revisa lo que preguntaron los empleados en «Employee questions».",
        en: "On the console's dashboard, see what employees asked under “Employee questions”.",
      },
    ] as Bi[],
    repo: { es: "El proyecto en GitHub", en: "The project on GitHub" },
  },
};

const FRAME = "font-sans border-dashed border-zinc-600 bg-zinc-900 text-zinc-100";

function Tag() {
  const t = useT();
  return <span className="font-mono text-[0.65rem] uppercase tracking-[0.12em] text-zinc-400">{t(GUIDE.tag)}</span>;
}

function ConsoleLink({ className }: { className?: string }) {
  const t = useT();
  return (
    <a
      href="/"
      target="_blank"
      rel="noreferrer"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md bg-zinc-100 px-3 py-1.5 font-semibold text-zinc-900 transition-colors hover:bg-white",
        className,
      )}
    >
      {t(GUIDE.console)} <ArrowUpRight className="size-4" />
    </a>
  );
}

function HideButton({ onClick }: { onClick: () => void }) {
  const t = useT();
  return (
    <button
      type="button"
      onClick={onClick}
      title={t(GUIDE.hide)}
      aria-label={t(GUIDE.hide)}
      className="grid size-8 shrink-0 place-items-center rounded-md text-zinc-400 hover:bg-white/10 hover:text-white"
    >
      <X className="size-4" />
    </button>
  );
}

/** The whole guide for one layout: its bar (strip or banner), the pill and the panel. */
export function DemoGuide({ where }: { where: "site" | "intranet" }) {
  const t = useT();
  const [mode, setMode] = useDemoGuide();
  const [panelOpen, setPanelOpen] = useState(false);
  const { pathname } = useLocation();
  const step = where === "site" ? (pathname.startsWith("/site/staff") ? 1 : 0) : 2;
  const reopen = useCallback(() => {
    setMode("open");
    setPanelOpen(true);
  }, [setMode]);

  return (
    <>
      {mode === "open" && where === "site" && (
        <div role="region" aria-label={t(GUIDE.pill)} className={cn(FRAME, "border-b")}>
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-xs sm:px-6">
            <Tag />
            <p className="text-zinc-200">
              {t(GUIDE.strip)}{" "}
              <Link to="/site/staff" className="inline-flex items-center gap-1 font-semibold text-white underline underline-offset-2 hover:no-underline">
                {t(GUIDE.path)} <ArrowRight className="size-3.5" />
              </Link>
            </p>
            <div className="ml-auto flex items-center gap-1">
              <button type="button" onClick={() => setPanelOpen(true)} className="rounded-md px-2 py-1 font-medium text-zinc-300 underline-offset-2 hover:text-white hover:underline">
                {t(GUIDE.how)}
              </button>
              <HideButton onClick={() => setMode("pill")} />
            </div>
          </div>
        </div>
      )}

      {mode === "open" && where === "intranet" && (
        <div role="region" aria-label={t(GUIDE.pill)} className={cn(FRAME, "border-b")}>
          <div className="mx-auto flex max-w-6xl items-start gap-3 px-4 py-3 sm:px-6">
            <Compass className="mt-0.5 size-5 shrink-0 text-zinc-400 max-sm:hidden" />
            <div className="min-w-0 flex-1 space-y-2">
              <Tag />
              <p className="text-sm text-zinc-200">{t(GUIDE.banner)}</p>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <button
                  type="button"
                  onClick={() => setPanelOpen(true)}
                  className="rounded-md border border-zinc-600 px-3 py-1.5 font-semibold text-zinc-100 transition-colors hover:bg-white/10"
                >
                  {t(GUIDE.how)}
                </button>
                <ConsoleLink />
              </div>
            </div>
            <HideButton onClick={() => setMode("pill")} />
          </div>
        </div>
      )}

      {mode === "pill" && (
        <button
          type="button"
          onClick={reopen}
          className={cn(FRAME, "fixed bottom-4 left-4 z-40 flex items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-semibold shadow-lg hover:bg-zinc-800")}
        >
          <Compass className="size-4 text-zinc-400" /> {t(GUIDE.pill)}
        </button>
      )}

      <Dialog
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        side="right"
        closeLabel={t(GUIDE.close)}
        className="font-sans"
        title={
          <span className="flex flex-col gap-1">
            <span className="font-mono text-[0.65rem] font-normal uppercase tracking-[0.12em] text-muted-foreground">{t(GUIDE.tag)}</span>
            {t(GUIDE.how)}
          </span>
        }
        description={t(GUIDE.panel.lede)}
        footer={
          <div className="flex w-full flex-wrap items-center justify-between gap-2 text-sm">
            <a href={REPO} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-muted-foreground hover:text-foreground hover:underline">
              <BookOpen className="size-4" /> {t(GUIDE.panel.repo)}
            </a>
            <ConsoleLink />
          </div>
        }
      >
        <div className="space-y-6 text-sm leading-relaxed">
          <section>
            <h3 className="font-semibold">{t(GUIDE.panel.whatTitle)}</h3>
            <p className="mt-1 text-muted-foreground">{t(GUIDE.panel.what)}</p>
          </section>
          <section>
            <h3 className="font-semibold">{t(GUIDE.panel.pathTitle)}</h3>
            <ol className="mt-2 space-y-2">
              {GUIDE.panel.steps.map((s, i) => (
                <li
                  key={s.title.en}
                  aria-current={i === step ? "step" : undefined}
                  className={cn("flex gap-3 rounded-md border p-3", i === step ? "border-zinc-900 bg-zinc-50" : "border-border")}
                >
                  <span
                    className={cn(
                      "grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold",
                      i === step ? "bg-zinc-900 text-white" : "bg-muted text-muted-foreground",
                    )}
                  >
                    {i + 1}
                  </span>
                  <div>
                    <p className="font-medium">
                      {t(s.title)}
                      {i === step && (
                        <span className="ml-2 rounded bg-zinc-900 px-1.5 py-0.5 font-mono text-[0.6rem] uppercase tracking-wider text-white">
                          {t(GUIDE.panel.here)}
                        </span>
                      )}
                    </p>
                    <p className="text-muted-foreground">{t(s.body)}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
          <section>
            <h3 className="font-semibold">{t(GUIDE.panel.tryTitle)}</h3>
            <ul className="mt-2 list-disc space-y-1.5 pl-5 text-muted-foreground">
              {GUIDE.panel.tries.map((item) => (
                <li key={item.en}>{t(item)}</li>
              ))}
            </ul>
          </section>
        </div>
      </Dialog>
    </>
  );
}
