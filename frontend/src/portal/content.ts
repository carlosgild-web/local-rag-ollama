/**
 * The portal's static pages, written from the fictional demo documents in
 * backend/demo/hilda-luna/ (handbook, holiday announcement, safety manual,
 * Q3 sales notes). Questions people have go to Luna, who answers from the
 * indexed documents themselves, with sources.
 */
import type { Bi } from "./i18n";

export const COMPANY = {
  name: "Hilda & Luna Beadworks",
  founded: 2015,
  employees: "~85",
  city: "Monterrey, Nuevo León",
  address: "Av. de los Artesanos 148",
  hrEmail: "hr@hildaluna-sample.com",
};

export const HERO = {
  eyebrow: { es: "Intranet · solo personal", en: "Intranet · staff only" },
  greeting: {
    morning: { es: "Buenos días, equipo", en: "Good morning, team" },
    afternoon: { es: "Buenas tardes, equipo", en: "Good afternoon, team" },
    evening: { es: "Buenas noches, equipo", en: "Good evening, team" },
  },
  title: {
    es: "Todo lo que necesitas del taller, en un solo lugar.",
    en: "Everything you need from the workshop, in one place.",
  },
  lede: {
    es: "Políticas, horarios y avisos del Estudio, el Taller, el Almacén y la Oficina. Y si no lo encuentras, pregúntale a Luna.",
    en: "Policies, schedules and notices for the Studio, Workshop, Warehouse and Office. And if you can't find it, ask Luna.",
  },
};

export interface SeasonItem {
  /** ISO dates; `end` for ranges. */
  start: string;
  end?: string;
  title: Bi;
  detail: Bi;
  ask: Bi;
}

/** The 2026 holiday season, in order (holiday announcement). */
export const SEASON: SeasonItem[] = [
  {
    start: "2026-11-07",
    end: "2026-12-12",
    title: { es: "Turnos de sábado en Producción", en: "Saturday production shifts" },
    detail: {
      es: "Voluntarios, de 8:00 a 14:00, pagados a 1.5×.",
      en: "Voluntary, 8:00 AM to 2:00 PM, paid at 1.5×.",
    },
    ask: { es: "¿Cómo se pagan los turnos de sábado?", en: "How are Saturday shifts paid?" },
  },
  {
    start: "2026-12-08",
    title: { es: "Fecha límite para confirmar la posada", en: "Holiday party RSVP deadline" },
    detail: {
      es: "Confirma en el portal. Cada persona puede llevar un invitado.",
      en: "RSVP in the portal. Each employee may bring one guest.",
    },
    ask: { es: "¿Puedo llevar un invitado a la fiesta?", en: "Can I bring a guest to the holiday party?" },
  },
  {
    start: "2026-12-12",
    title: { es: "Venta de Scrap Bin, edición navideña", en: "Scrap Bin Sale, holiday edition" },
    detail: {
      es: "10:00 a 13:00 en el andén del Almacén. Efectivo o crédito del portal.",
      en: "10:00 AM to 1:00 PM at the Warehouse loading dock. Cash or portal credit.",
    },
    ask: { es: "¿Dónde y cuándo es la venta de Scrap Bin?", en: "Where and when is the Scrap Bin Sale?" },
  },
  {
    start: "2026-12-18",
    title: { es: "Fiesta de fin de año y bono", en: "Holiday party and bonus" },
    detail: {
      es: "18:00 a 22:00 en el piso del Taller. El reparto de utilidades llega con la nómina de este día.",
      en: "6:00 to 10:00 PM on the Workshop floor. Profit-sharing is paid with this day's paycheck.",
    },
    ask: {
      es: "¿Cuándo se paga el bono de reparto de utilidades este año?",
      en: "When is the profit-sharing bonus paid this year?",
    },
  },
  {
    start: "2026-12-22",
    end: "2027-01-02",
    title: { es: "Cierre por fiestas", en: "Holiday closure" },
    detail: {
      es: "Taller, Estudio, Almacén y Oficina cerrados. Reabrimos el lunes 3 de enero de 2027.",
      en: "Workshop, Studio, Warehouse and Office closed. We reopen Monday, January 3, 2027.",
    },
    ask: { es: "¿Cuándo cierra la empresa por las fiestas?", en: "When does the company close for the holidays?" },
  },
];

export interface HandbookTopic {
  figure: Bi;
  title: Bi;
  detail: Bi;
  ask: Bi;
}

/** Quick answers from the employee handbook; each one opens Luna. */
export const HANDBOOK: HandbookTopic[] = [
  {
    figure: { es: "12 · 16 · 20 días", en: "12 · 16 · 20 days" },
    title: { es: "Vacaciones (PTO)", en: "Paid time off" },
    detail: {
      es: "Según antigüedad: años 1–2, 3–5 y 6 en adelante. Solicítalas con 2 semanas de anticipación.",
      en: "By tenure: years 1–2, 3–5 and 6+. Request them 2 weeks ahead.",
    },
    ask: { es: "¿Cuántos días de vacaciones tengo en mi tercer año?", en: "How many PTO days do I get in my third year?" },
  },
  {
    figure: { es: "2 días / semana", en: "2 days / week" },
    title: { es: "Trabajo remoto", en: "Remote work" },
    detail: {
      es: "Oficina y Estudio, después de 6 meses y con aprobación. Producción y Almacén, no.",
      en: "Office and Studio roles, after 6 months and with approval. Not Production or Warehouse.",
    },
    ask: { es: "¿Puedo trabajar desde casa?", en: "Can I work from home?" },
  },
  {
    figure: { es: "70 %", en: "70%" },
    title: { es: "Seguro médico", en: "Health insurance" },
    detail: {
      es: "La empresa cubre el 70 % de la prima. Tiempo completo, después de 60 días.",
      en: "The company covers 70% of the premium. Full-time, after 60 days.",
    },
    ask: { es: "¿Qué beneficios tengo como empleado de tiempo completo?", en: "What benefits do full-time employees get?" },
  },
  {
    figure: { es: "40 % · 25 %", en: "40% · 25%" },
    title: { es: "Descuento de empleado", en: "Employee discount" },
    detail: {
      es: "40 % en joyería terminada y 25 % en cuentas y dijes sueltos.",
      en: "40% off finished jewelry and 25% off loose beads and charms.",
    },
    ask: { es: "¿Qué descuento tengo en cuentas sueltas?", en: "What discount do I get on loose beads?" },
  },
  {
    figure: { es: "12 semanas", en: "12 weeks" },
    title: { es: "Licencia parental", en: "Parental leave" },
    detail: {
      es: "Las primeras 6 semanas al 100 % del salario base.",
      en: "The first 6 weeks at 100% of base salary.",
    },
    ask: { es: "¿Cómo funciona la licencia parental?", en: "How does parental leave work?" },
  },
  {
    figure: { es: "Nitrilo, no látex", en: "Nitrile, not latex" },
    title: { es: "Seguridad en el Taller", en: "Workshop safety" },
    detail: {
      es: "Lentes para vidrio en sopletes y hornos; resina solo bajo campana en la Bahía 3.",
      en: "Glassworking glasses at torches and kilns; resin only under the Bay 3 hoods.",
    },
    ask: { es: "¿Qué guantes debo usar para trabajar con resina?", en: "Which gloves should I use for resin work?" },
  },
];

export interface Shift {
  department: Bi;
  hours: Bi;
  note: Bi;
}

/** Standard hours by department (handbook section 3.1). */
export const HOURS: Shift[] = [
  {
    department: { es: "Estudio de Diseño", en: "Design Studio" },
    hours: { es: "9:00 – 18:00", en: "9:00 AM – 6:00 PM" },
    note: { es: "1 h de comida, no pagada", en: "1-hour unpaid lunch" },
  },
  {
    department: { es: "Taller de Producción", en: "Production Workshop" },
    hours: { es: "7:00 – 15:30 · 15:30 – 0:00", en: "7:00 AM – 3:30 PM · 3:30 PM – 12:00 AM" },
    note: { es: "Dos turnos; rotan cada mes", en: "Two shifts; rotate monthly" },
  },
  {
    department: { es: "Almacén y Envíos", en: "Warehouse & Shipping" },
    hours: { es: "8:00 – 17:00", en: "8:00 AM – 5:00 PM" },
    note: { es: "Horas extra comunes en nov–dic", en: "Overtime common Nov–Dec" },
  },
  {
    department: { es: "Oficina y Administración", en: "Office & Administration" },
    hours: { es: "9:00 – 18:00", en: "9:00 AM – 6:00 PM" },
    note: { es: "Híbrido después de 6 meses", en: "Hybrid after 6 months" },
  },
];

export interface NewsItem {
  kicker: Bi;
  title: Bi;
  body: Bi;
  source: string;
  ask: Bi;
}

/** From the Q3 2026 sales review (October 6, 2026). */
export const NEWS: NewsItem[] = [
  {
    kicker: { es: "Lanzamiento", en: "Launch" },
    title: { es: "Amber Hollow ya está a la venta", en: "Amber Hollow is out" },
    body: {
      es: "La colección salió el 15 de octubre con 340 preventas. El Almacén instaló estantería extra en la Bahía 2.",
      en: "The collection launched on October 15 with 340 pre-orders. The Warehouse added shelving in Bay 2.",
    },
    source: "07-q3-2026-sales-meeting-notes.txt",
    ask: { es: "¿Cómo va el lanzamiento de Amber Hollow?", en: "How is the Amber Hollow launch going?" },
  },
  {
    kicker: { es: "Más vendido", en: "Best seller" },
    title: { es: "4,120 dijes Crescent Moon & Star", en: "4,120 Crescent Moon & Star charms" },
    body: {
      es: "El CH-2004 fue el producto más vendido del tercer trimestre; en cuentas, la GB-1014 Opal Mist Swirl.",
      en: "CH-2004 was Q3's best-selling item; among beads, GB-1014 Opal Mist Swirl.",
    },
    source: "07-q3-2026-sales-meeting-notes.txt",
    ask: { es: "¿Cuál fue el producto más vendido en el tercer trimestre?", en: "What was the best-selling product in Q3?" },
  },
  {
    kicker: { es: "Resultados", en: "Results" },
    title: { es: "Ingresos del T3, 18 % arriba", en: "Q3 revenue up 18%" },
    body: {
      es: "Mayoreo aportó el 61 % de los ingresos. Dos tiendas nuevas: Thistle & Thread (Austin) y Casa de Cuentas (Querétaro).",
      en: "Wholesale brought 61% of revenue. Two new boutiques: Thistle & Thread (Austin) and Casa de Cuentas (Querétaro).",
    },
    source: "07-q3-2026-sales-meeting-notes.txt",
    ask: { es: "¿Qué clientes de mayoreo nuevos tuvimos en el T3?", en: "Which new wholesale accounts did we get in Q3?" },
  },
];

/** Starter questions in Luna's empty state. */
export const SUGGESTIONS: Bi[] = [
  { es: "¿Cuántos días de vacaciones tengo en mi tercer año?", en: "How many PTO days do I get in my third year?" },
  { es: "¿Cuándo cierra la empresa por las fiestas?", en: "When does the company close for the holidays?" },
  { es: "¿Qué guantes debo usar para trabajar con resina?", en: "Which gloves should I use for resin work?" },
  { es: "¿Cuál es la política de devoluciones?", en: "What is the returns policy?" },
];

export const SECTIONS = {
  season: {
    title: { es: "Esta temporada", en: "This season" },
    note: {
      es: "Fechas del aviso de fiestas 2026.",
      en: "Dates from the 2026 holiday announcement.",
    },
    today: { es: "Hoy", en: "Today" },
    now: { es: "En curso", en: "Now" },
    done: { es: "Terminado", en: "Done" },
  },
  handbook: {
    title: { es: "El manual, en corto", en: "The handbook, in short" },
    note: {
      es: "Lo que más se pregunta. Toca una tarjeta para preguntarle a Luna los detalles.",
      en: "What people ask most. Tap a card to ask Luna for the details.",
    },
  },
  hours: {
    title: { es: "Horarios por área", en: "Hours by department" },
    department: { es: "Área", en: "Department" },
    hours: { es: "Horario", en: "Hours" },
    note: { es: "Nota", en: "Note" },
  },
  news: {
    title: { es: "Noticias", en: "News" },
    note: {
      es: "De la revisión de ventas del T3 (6 de octubre de 2026).",
      en: "From the Q3 sales review (October 6, 2026).",
    },
  },
  company: {
    title: { es: "La empresa", en: "The company" },
    founded: { es: "Fundada", en: "Founded" },
    people: { es: "Personas", en: "People" },
    hq: { es: "Sede", en: "Headquarters" },
    hr: { es: "Recursos Humanos", en: "Human Resources" },
    what: {
      es: "Diseñamos y fabricamos a mano cuentas y dijes de vidrio, resina y metal para artesanos joyeros, aficionados y tiendas de mayoreo.",
      en: "We design and handmake glass, resin and metal beads and charms for jewelry artisans, hobby crafters and wholesale retailers.",
    },
  },
  ask: { es: "Preguntar a Luna", en: "Ask Luna" },
};
