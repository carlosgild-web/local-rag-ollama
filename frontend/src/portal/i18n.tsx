import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

/** The portal's two languages. The model is asked to answer in the same one. */
export type Lang = "es" | "en";

const STORAGE_KEY = "hl-portal-lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "es" || saved === "en") return saved;
  } catch {
    // storage blocked (private window): fall back to the browser language
  }
  return navigator.language?.toLowerCase().startsWith("es") ? "es" : "en";
}

interface LangState {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

const LangContext = createContext<LangState | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // not remembered; still switches for this visit
    }
  }, []);

  useEffect(() => {
    const previous = document.documentElement.lang;
    document.documentElement.lang = lang;
    return () => {
      document.documentElement.lang = previous;
    };
  }, [lang]);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangState {
  const state = useContext(LangContext);
  if (!state) throw new Error("useLang needs a LangProvider");
  return state;
}

/** Picks the current language's value from an `{ es, en }` pair. */
export type Bi<T = string> = { es: T; en: T };

export function useT() {
  const { lang } = useLang();
  return useCallback(<T,>(pair: Bi<T>): T => pair[lang], [lang]);
}

/** Interface strings. Content (news, handbook, dates) lives in content.ts. */
export const UI = {
  nav: {
    home: { es: "Inicio", en: "Home" },
    season: { es: "Temporada", en: "This season" },
    handbook: { es: "Manual", en: "Handbook" },
    news: { es: "Noticias", en: "News" },
    luna: { es: "Pregúntale a Luna", en: "Ask Luna" },
    menu: { es: "Menú", en: "Menu" },
  },
  langLabel: { es: "Idioma", en: "Language" },
  skip: { es: "Saltar al contenido", en: "Skip to content" },
  footer: {
    fictional: {
      es: "Hilda & Luna Beadworks es una empresa ficticia. Acceso interno simulado, sin inicio de sesión.",
      en: "Hilda & Luna Beadworks is a fictional company. Simulated internal access, no sign-in.",
    },
    local: {
      es: "Luna responde solo con los documentos del sistema RAG local. Nada sale de esta computadora.",
      en: "Luna answers only from documents in the local RAG system. Nothing leaves this computer.",
    },
    console: { es: "Consola RAG", en: "RAG console" },
    site: { es: "Sitio público", en: "Public website" },
  },
  luna: {
    name: "Luna",
    tagline: {
      es: "Tu asistente para políticas, horarios y procesos de la empresa.",
      en: "Your assistant for company policies, schedules and processes.",
    },
    placeholder: { es: "Escribe tu pregunta…", en: "Type your question…" },
    heroPlaceholder: {
      es: "Pregúntale a Luna: ¿cuántos días de vacaciones tengo?",
      en: "Ask Luna: how many vacation days do I get?",
    },
    send: { es: "Enviar", en: "Send" },
    stop: { es: "Detener", en: "Stop" },
    newChat: { es: "Nueva conversación", en: "New conversation" },
    open: { es: "Abrir chat con Luna", en: "Open chat with Luna" },
    close: { es: "Cerrar chat", en: "Close chat" },
    expand: { es: "Abrir en pantalla completa", en: "Open full screen" },
    thinking: { es: "Luna está buscando en los documentos…", en: "Luna is searching the documents…" },
    stopped: { es: "Respuesta detenida.", en: "Answer stopped." },
    sources: { es: "Fuentes", en: "Sources" },
    page: { es: "pág.", en: "p." },
    loadingPassage: { es: "Cargando el fragmento…", en: "Loading the passage…" },
    passageError: { es: "No se pudo cargar el fragmento.", en: "Couldn't load this passage." },
    helpful: { es: "¿Te sirvió?", en: "Was this helpful?" },
    yes: { es: "Sí, me sirvió", en: "Yes, helpful" },
    no: { es: "No me sirvió", en: "Not helpful" },
    thanks: { es: "Gracias por tu opinión.", en: "Thanks for the feedback." },
    whatWrong: { es: "¿Qué estuvo mal? (opcional)", en: "What was wrong? (optional)" },
    suggestions: { es: "Prueba con", en: "Try asking" },
    recent: { es: "Tus conversaciones recientes", en: "Your recent conversations" },
    recentNote: {
      es: "Se guardan solo en este navegador.",
      en: "Kept in this browser only.",
    },
    welcome: {
      es: "Hola, soy Luna. Busco respuestas en los documentos internos de Hilda & Luna y siempre te digo de dónde salen.",
      en: "Hi, I'm Luna. I look for answers in Hilda & Luna's internal documents and always show you where they come from.",
    },
    notFoundTitle: {
      es: "No encontré esto en los documentos de la empresa.",
      en: "I couldn't find this in the company documents.",
    },
    notFoundBody: {
      es: "Prueba a preguntarlo de otra forma, o escribe a Recursos Humanos: hr@hildaluna-sample.com",
      en: "Try asking another way, or write to HR: hr@hildaluna-sample.com",
    },
    error: { es: "Luna no pudo responder", en: "Luna couldn't answer" },
    retry: { es: "Intentar de nuevo", en: "Try again" },
    disclaimer: {
      es: "Luna puede equivocarse. Revisa las fuentes antes de decidir algo importante.",
      en: "Luna can make mistakes. Check the sources before deciding anything important.",
    },
  },
} as const;
