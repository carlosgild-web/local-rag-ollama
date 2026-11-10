/**
 * The public website's text, written once from the customer-facing demo
 * documents in backend/demo/hilda-luna/ (decision 0011):
 *   - operations/01-product-catalog.pdf        products, collections, craft
 *   - operations/09-shipping-returns-policy.md  shipping, returns, damage
 *   - operations/10-wholesale-pricing-sheet.md  tiers, terms, starter sets
 *   - customer-support/08-customer-faq.txt      FAQ
 *   - hr/... HR Policy.docx, section 1          who we are (overview only)
 * Internal facts (sales figures, HR policy, holiday dates) stay on the intranet.
 * Like the intranet's pages, this text does not follow document changes.
 */
import type { Bi } from "@/portal/i18n";

export const SITE = {
  name: "Hilda & Luna Beadworks",
  founded: 2015,
  city: "Monterrey, Nuevo León",
  address: "Av. de los Artesanos 148",
  support: "support@hildaluna-sample.com",
  wholesale: "wholesale@hildaluna-sample.com",
};

/* ------------------------------------------------------------------ chrome */

export const NAV = {
  home: { es: "Inicio", en: "Home" },
  catalog: { es: "Catálogo", en: "Catalog" },
  wholesale: { es: "Mayoreo", en: "Wholesale" },
  help: { es: "Ayuda", en: "Help" },
  story: { es: "Nuestra historia", en: "Our story" },
  menu: { es: "Menú", en: "Menu" },
  skip: { es: "Saltar al contenido", en: "Skip to content" },
  tagline: { es: "Hecho a mano en Monterrey desde 2015", en: "Handmade in Monterrey since 2015" },
  wholesaleAccounts: { es: "Cuentas de mayoreo", en: "Wholesale accounts" },
  employeeLogin: { es: "Acceso empleados", en: "Employee login" },
  tab: { es: "Hilda & Luna Beadworks · Cuentas y dijes hechos a mano", en: "Hilda & Luna Beadworks · Handmade beads & charms" },
};

export const ANNOUNCE = {
  collection: { es: "Ya llegó Amber Hollow, la colección otoño-invierno", en: "Amber Hollow, our Fall/Winter collection, is here" },
  shipping: { es: "Envío nacional gratis en pedidos de $50 o más", en: "Free domestic shipping on retail orders of $50+" },
};

export const FOOTER = {
  care: { es: "Atención a clientes", en: "Customer care" },
  shipping: { es: "Envíos", en: "Shipping" },
  returns: { es: "Devoluciones", en: "Returns" },
  faq: { es: "Preguntas frecuentes", en: "FAQ" },
  contact: { es: "Contacto", en: "Contact" },
  company: { es: "La empresa", en: "Company" },
  employees: { es: "Empleados", en: "Employees" },
  staff: { es: "Acceso del personal", en: "Staff sign-in" },
  intranet: { es: "Intranet y Luna", en: "Intranet & Luna" },
  fictional: {
    es: "Hilda & Luna Beadworks es una empresa ficticia, creada para demostrar un sistema RAG local. No hay tienda: nada se vende ni se envía.",
    en: "Hilda & Luna Beadworks is a fictional company, made up to demo a local RAG system. There's no shop: nothing is sold or sent.",
  },
  console: { es: "Consola RAG", en: "RAG console" },
};

/* -------------------------------------------------------------------- home */

export const HERO = {
  eyebrow: { es: "Cuentas de vidrio y dijes de peltre, hechos a mano", en: "Handmade glass beads & pewter charms" },
  title: { es: "Cuentas pequeñas, hechas despacio y a mano.", en: "Small beads, made slowly, by hand." },
  lede: {
    es: "Diseñamos y fabricamos cuentas y dijes de vidrio, resina y metal para artesanos joyeros, aficionados y tiendas de mayoreo.",
    en: "We design and make glass, resin and metal beads and charms for jewelry artisans, hobby crafters and wholesale retailers.",
  },
  shop: { es: "Ver el catálogo", en: "Browse the catalog" },
  trade: { es: "Cuentas de mayoreo", en: "Wholesale accounts" },
  photoAlt: {
    es: "Un collar de cuentas de vidrio del catálogo con el dije dorado de luna creciente y estrella",
    en: "A necklace of glass beads from the catalog with the gold Crescent Moon & Star charm",
  },
};

export interface Collection {
  id: "amber-hollow" | "coastal-garden";
  name: string;
  season: Bi;
  status: Bi;
  body: Bi;
  palette: string[];
  charms: CharmKind[];
  /** Describes the banner photo (made with Google Gemini, docs/site-images.md). */
  photoAlt: Bi;
}

/** Catalog section 4 and the FAQ. */
export const COLLECTIONS: Collection[] = [
  {
    id: "amber-hollow",
    name: "Amber Hollow",
    season: { es: "Otoño-invierno 2026", en: "Fall/Winter 2026" },
    status: { es: "Nueva · desde el 15 de octubre", en: "New · since October 15" },
    body: {
      es: "Tonos cálidos de ámbar, óxido y verde bosque, con dijes de bellota, luna y hongo.",
      en: "Warm amber, rust and deep forest tones, paired with acorn, moon and mushroom charms.",
    },
    palette: ["#e39a2d", "#a8481f", "#2d5443", "#c87f3a", "#6b3a1f"],
    charms: ["acorn", "moon", "mushroom"],
    photoAlt: {
      es: "Cuentas de vidrio ámbar, óxido y verde bosque con dijes de bellota y hongo sobre madera oscura",
      en: "Amber, rust and forest-green glass beads with acorn and mushroom charms on dark wood",
    },
  },
  {
    id: "coastal-garden",
    name: "Coastal Garden",
    season: { es: "Primavera-verano 2026", en: "Spring/Summer 2026" },
    status: { es: "Temporada terminada en agosto", en: "Season ended in August" },
    body: {
      es: "Cuentas de vidrio en tonos pastel, con dijes botánicos y de conchas marinas.",
      en: "Pastel glass beads paired with botanical and seashell charms.",
    },
    palette: ["#e7a3a6", "#9fd3c7", "#f3d9a4", "#b9c8ea", "#5fae9c"],
    charms: ["shell", "leaf"],
    photoAlt: {
      es: "Cuentas de vidrio en tonos pastel con dijes de concha y hoja sobre lino claro",
      en: "Pastel glass beads with seashell and leaf charms on pale linen",
    },
  },
];

export const SECTIONS = {
  collections: {
    title: { es: "Colecciones de temporada", en: "Seasonal collections" },
    note: { es: "Dos lanzamientos al año, en lotes pequeños.", en: "Two releases a year, in small batches." },
    cta: { es: "Ver en el catálogo", en: "See it in the catalog" },
  },
  shopBy: {
    title: { es: "Explora por tipo", en: "Shop by type" },
  },
  favorites: {
    title: { es: "Favoritos de nuestros clientes", en: "Customer favorites" },
    all: { es: "Todo el catálogo", en: "The full catalog" },
    best: { es: "Más vendido", en: "Best seller" },
  },
  story: {
    eyebrow: { es: "Nuestra historia", en: "Our story" },
    title: { es: "Un taller de vidrio y metal en Monterrey.", en: "A glass and metal workshop in Monterrey." },
    body: {
      es: "Desde 2015 diseñamos cada colección en nuestro Estudio y la hacemos en nuestro Taller: cuentas de vidrio enrolladas a mano, dijes diseñados aquí y fundidos en peltre sin plomo, y pedidos empacados en nuestro propio Almacén.",
      en: "Since 2015 we have designed every collection in our Studio and made it in our Workshop: glass beads wound by hand, charms designed here and cast in lead-free pewter, and orders packed in our own Warehouse.",
    },
    photoAlt: {
      es: "Manos enrollando una cuenta de vidrio en el soplete, en el taller",
      en: "An artisan's hands winding a glass bead at the torch in the workshop",
    },
  },
  trade: {
    eyebrow: { es: "Mayoreo", en: "Wholesale" },
    title: { es: "¿Vendes joyería o materiales?", en: "Selling jewelry or supplies?" },
    body: {
      es: "Las tiendas compran desde $150 por pedido, con 45–50 % de descuento sobre el precio de menudeo.",
      en: "Boutiques buy from $150 an order, at 45–50% off retail.",
    },
    cta: { es: "Cómo abrir una cuenta", en: "How to open an account" },
  },
  newsletter: {
    title: { es: "Sé de los primeros en enterarte", en: "Hear about it first" },
    body: {
      es: "Quienes están en nuestra lista se enteran primero de las ventas de Scrap Bin y de los colores de edición limitada.",
      en: "People on our list hear first about Scrap Bin sales and limited-release colorways.",
    },
    email: { es: "Tu correo electrónico", en: "Your email address" },
    submit: { es: "Suscribirme", en: "Sign me up" },
  },
};

export const CRAFT: { title: Bi; body: Bi }[] = [
  {
    title: { es: "Vidrio enrollado a mano", en: "Hand-wound glass" },
    body: {
      es: "Varilla de vidrio borosilicato y sódico-cálcico, en lotes de 200 a 400 cuentas por color.",
      en: "Borosilicate and soda-lime glass rod, in runs of 200 to 400 beads per color.",
    },
  },
  {
    title: { es: "Peltre sin plomo", en: "Lead-free pewter" },
    body: {
      es: "Dijes fundidos en aleación de peltre sin plomo, con baño de oro de 14k, rodio o bronce antiguo.",
      en: "Charms cast in lead-free pewter alloy, finished in 14k gold plate, rhodium or antique bronze.",
    },
  },
  {
    title: { es: "De nuestro taller a tu mesa", en: "From our bench to yours" },
    body: {
      es: "Diseño, producción y envíos en un mismo equipo. Los pedidos de menudeo salen en 1 a 3 días hábiles.",
      en: "Design, production and shipping in one team. Retail orders ship in 1 to 3 business days.",
    },
  },
];

/* ----------------------------------------------------------------- catalog */

export type BeadShape = "round" | "faceted" | "swirl" | "lentil";
export type CharmKind = "moon" | "bee" | "lotus" | "cactus" | "initial" | "acorn" | "mushroom" | "shell" | "leaf";
export type Finish = "gold" | "rhodium" | "bronze";
export type FindingKind = "rings" | "clasp" | "wire" | "memory";
export type Category = "beads" | "charms" | "findings";

export interface BeadProduct {
  sku: string;
  name: string;
  size: string;
  price: number;
  shape: BeadShape;
  colors: [string, string];
}

export interface CharmProduct {
  sku: string;
  name: Bi;
  finish: Finish;
  price: number;
  kind: CharmKind;
}

export interface Finding {
  kind: FindingKind;
  name: Bi;
  detail: Bi;
}

/** Catalog section 1. Retail prices in USD, each. */
export const BEADS: BeadProduct[] = [
  { sku: "GB-1001", name: "Midnight Lagoon Round", size: "8 mm", price: 0.75, shape: "round", colors: ["#1f4f7a", "#2f8a8f"] },
  { sku: "GB-1002", name: "Desert Sand Faceted", size: "10 mm", price: 1.0, shape: "faceted", colors: ["#d8b384", "#b98d5c"] },
  { sku: "GB-1014", name: "Opal Mist Swirl", size: "12 mm", price: 1.6, shape: "swirl", colors: ["#eadfe8", "#b9c8ea"] },
  { sku: "GB-1027", name: "Terracotta Sunrise", size: "8 mm", price: 0.8, shape: "round", colors: ["#c8643b", "#e39a2d"] },
  { sku: "GB-1033", name: "Deep Forest Lentil", size: "14 mm", price: 1.95, shape: "lentil", colors: ["#2d5443", "#5d8a5e"] },
];

/** Catalog section 2. */
export const CHARMS: CharmProduct[] = [
  { sku: "CH-2004", name: { es: "Luna creciente y estrella", en: "Crescent Moon & Star" }, finish: "gold", price: 1.85, kind: "moon" },
  { sku: "CH-2011", name: { es: "Abejita", en: "Tiny Honeybee" }, finish: "bronze", price: 1.5, kind: "bee" },
  { sku: "CH-2019", name: { es: "Flor de nacimiento: loto", en: "Birth Flower — Lotus" }, finish: "rhodium", price: 2.1, kind: "lotus" },
  { sku: "CH-2026", name: { es: "Cactus del desierto", en: "Desert Cactus" }, finish: "gold", price: 1.75, kind: "cactus" },
  { sku: "CH-2033", name: { es: "Inicial manuscrita (A–Z)", en: "Script Initial (A–Z)" }, finish: "gold", price: 1.4, kind: "initial" },
];

/** Catalog section 3. Findings are sold individually (FAQ). */
export const FINDINGS: Finding[] = [
  {
    kind: "rings",
    name: { es: "Argollas", en: "Jump rings" },
    detail: { es: "4, 6 y 8 mm · plata esterlina, gold-filled o metal base", en: "4, 6 and 8 mm · sterling silver, gold-filled or base metal" },
  },
  {
    kind: "clasp",
    name: { es: "Broches de langosta", en: "Lobster clasps" },
    detail: { es: "12 y 15 mm · baño de oro o rodio", en: "12 and 15 mm · gold plate or rhodium" },
  },
  {
    kind: "wire",
    name: { es: "Hilo para cuentas", en: "Beading wire" },
    detail: { es: "0.3 mm, acero inoxidable con nylon · carretes de 10 m", en: "0.3 mm nylon-coated stainless · 10 m spools" },
  },
  {
    kind: "memory",
    name: { es: "Alambre con memoria", en: "Memory wire" },
    detail: { es: "Calibre de pulsera y de collar · acero oxidado", en: "Bracelet and necklace gauge · oxidized steel" },
  },
];

export const FINISH: Record<Finish, { label: Bi; nickel: Bi; nickelFree: boolean }> = {
  gold: {
    label: { es: "Baño de oro", en: "Gold plate" },
    nickel: { es: "Sin níquel", en: "Nickel-free" },
    nickelFree: true,
  },
  rhodium: {
    label: { es: "Rodio", en: "Rhodium" },
    nickel: { es: "Sin níquel", en: "Nickel-free" },
    nickelFree: true,
  },
  bronze: {
    label: { es: "Bronce antiguo", en: "Antique bronze" },
    nickel: { es: "Trazas de níquel", en: "Trace nickel" },
    nickelFree: false,
  },
};

export const CATALOG = {
  eyebrow: { es: "Catálogo otoño-invierno 2026", en: "Fall/Winter 2026 catalog" },
  title: { es: "Cuentas, dijes y avíos", en: "Beads, charms and findings" },
  lede: {
    es: "Precios de menudeo en dólares (USD), por pieza. Con una cuenta de mayoreo pagas precio de mayoreo desde 12 piezas.",
    en: "Retail prices in US dollars, per piece. Wholesale accounts get trade pricing from 12 pieces.",
  },
  tabs: {
    beads: { es: "Cuentas de vidrio", en: "Glass beads" },
    charms: { es: "Dijes", en: "Charms" },
    findings: { es: "Avíos", en: "Findings" },
  } satisfies Record<Category, Bi>,
  tabNotes: {
    beads: {
      es: "Enrolladas a mano en el taller, con varilla de vidrio borosilicato y sódico-cálcico.",
      en: "Hand-wound in our workshop from borosilicate and soda-lime glass rod.",
    },
    charms: {
      es: "Peltre sin plomo. El oro y el rodio no tienen níquel; el bronce antiguo tiene trazas, así que si tienes sensibilidad elige oro o rodio.",
      en: "Lead-free pewter. Gold plate and rhodium are nickel-free; antique bronze has trace nickel, so choose gold or rhodium if you're sensitive.",
    },
    findings: {
      es: "Se venden por separado y no se incluyen en el precio de las cuentas o los dijes, salvo en un kit.",
      en: "Sold individually, and not included in bead or charm prices unless they're part of a kit.",
    },
  } satisfies Record<Category, Bi>,
  each: { es: "c/u", en: "each" },
  trade: { es: "Precio de mayoreo con cuenta", en: "Trade price with an account" },
  individually: { es: "Se vende por separado", en: "Sold individually" },
  tiers: {
    title: { es: "Mínimos por tipo de cliente", en: "Minimum order by customer type" },
    rows: [
      { who: { es: "Aficionados (menudeo)", en: "Hobbyist (retail)" }, min: { es: "Sin mínimo", en: "No minimum" }, ships: { es: "1–3 días hábiles", en: "1–3 business days" } },
      { who: { es: "Tiendas (mayoreo)", en: "Boutique wholesale" }, min: { es: "$150 por pedido", en: "$150 per order" }, ships: { es: "5–7 días hábiles", en: "5–7 business days" } },
      { who: { es: "Mayoristas y distribuidores", en: "Large wholesale / distributor" }, min: { es: "$750 por pedido", en: "$750 per order" }, ships: { es: "10–14 días hábiles", en: "10–14 business days" } },
    ],
    who: { es: "Cliente", en: "Customer" },
    min: { es: "Pedido mínimo", en: "Minimum order" },
    ships: { es: "Sale en", en: "Ships in" },
  },
};

/* --------------------------------------------------------------- wholesale */

export interface Tier {
  name: Bi;
  minimum: Bi;
  discount: string;
  terms: Bi;
  note?: Bi;
  featured?: boolean;
}

/** Pricing sheet section 1. */
export const TIERS: Tier[] = [
  {
    name: { es: "Tienda", en: "Boutique" },
    minimum: { es: "$150 por pedido", en: "$150 per order" },
    discount: "45–50%",
    terms: { es: "Neto 15, o 2 % extra si pagas por adelantado", en: "Net 15, or an extra 2% off when you prepay" },
    note: { es: "Sale en 5–7 días hábiles", en: "Ships in 5–7 business days" },
  },
  {
    name: { es: "Mayorista / distribuidor", en: "Large wholesale / distributor" },
    minimum: { es: "$750 por pedido", en: "$750 per order" },
    discount: "55–60%",
    terms: { es: "Neto 30", en: "Net 30" },
    note: { es: "Envío nacional gratis en México · 10–14 días hábiles", en: "Free domestic shipping in Mexico · 10–14 business days" },
    featured: true,
  },
  {
    name: { es: "Socio estratégico", en: "Strategic partner" },
    minimum: { es: "$2,500+ por trimestre", en: "$2,500+ per quarter" },
    discount: "60–65%",
    terms: { es: "Neto 45", en: "Net 45" },
    note: { es: "Solo por invitación", en: "By invitation only" },
  },
];

export interface StarterSet {
  name: Bi;
  contents: Bi;
  boutique: number;
  large: number;
}

/** Pricing sheet section 4. */
export const STARTER_SETS: StarterSet[] = [
  {
    name: { es: "Set inicial Coastal Garden", en: "Coastal Garden Starter Set" },
    contents: { es: "200 cuentas + 50 dijes, varios SKU", en: "200 beads + 50 charms, mixed SKUs" },
    boutique: 142,
    large: 118,
  },
  {
    name: { es: "Set inicial Amber Hollow", en: "Amber Hollow Starter Set" },
    contents: { es: "200 cuentas + 50 dijes, varios SKU", en: "200 beads + 50 charms, mixed SKUs" },
    boutique: 148,
    large: 123,
  },
  {
    name: { es: "Kit básico de avíos", en: "Findings Essentials Kit" },
    contents: { es: "500 argollas, 100 broches, 2 carretes de hilo", en: "500 jump rings, 100 clasps, 2 wire spools" },
    boutique: 64,
    large: 52,
  },
];

export const WHOLESALE = {
  eyebrow: { es: "Para tiendas y distribuidores", en: "For boutiques and distributors" },
  title: { es: "Vende cuentas hechas a mano en tu tienda.", en: "Stock handmade beads in your shop." },
  lede: {
    es: "Tres niveles según el tamaño de tu pedido. Precios vigentes del 1 de octubre al 31 de diciembre de 2026, en USD.",
    en: "Three tiers, by order size. Prices valid October 1 to December 31, 2026, in USD.",
  },
  tiersTitle: { es: "Niveles de mayoreo", en: "Wholesale tiers" },
  off: { es: "de descuento sobre menudeo", en: "off retail" },
  steps: {
    title: { es: "Cómo abrir una cuenta", en: "How to open an account" },
    items: [
      {
        title: { es: "Envía tu solicitud", en: "Send your application" },
        body: { es: "Con tu licencia comercial o tu certificado de reventa.", en: "With your business license or resale certificate." },
      },
      {
        title: { es: "Te aprobamos en 3–5 días hábiles", en: "Approval in 3–5 business days" },
        body: { es: "Te asignamos un ejecutivo de cuenta.", en: "We assign you an account manager." },
      },
      {
        title: { es: "Haz tu primer pedido", en: "Place your first order" },
        body: { es: "Los precios de una orden de compra aprobada se respetan 60 días.", en: "Prices on an approved purchase order are honored for 60 days." },
      },
    ],
  },
  custom: {
    title: { es: "Colores a la medida", en: "Custom color runs" },
    body: {
      es: "Evaluamos cada solicitud por separado. En general piden un mínimo de 2 kg de vidrio por color y tardan de 15 a 20 días hábiles después de aprobar el color.",
      en: "We look at each request case by case. They generally need at least 2 kg of glass per color, and take 15 to 20 business days after the color is approved.",
    },
    final: { es: "Los pedidos de color a la medida no admiten devolución.", en: "Custom color orders are final sale." },
    ask: { es: "Pide una cotización:", en: "Ask for a quote:" },
  },
  sets: {
    title: { es: "Sets iniciales", en: "Starter sets" },
    note: { es: "Una forma fácil de empezar a vender una colección.", en: "An easy way to start carrying a collection." },
    set: { es: "Set", en: "Set" },
    contents: { es: "Contenido", en: "Contents" },
    boutique: { es: "Tienda", en: "Boutique" },
    large: { es: "Mayorista", en: "Large" },
  },
  terms: {
    title: { es: "Bueno saber", en: "Good to know" },
    items: [
      {
        es: "Revisamos precios cada trimestre y avisamos con 30 días de anticipación a las cuentas activas.",
        en: "Prices are reviewed every quarter, with 30 days' notice to active accounts.",
      },
      {
        es: "Los pedidos de tienda pagan el envío según la tarifa del transportista.",
        en: "Boutique orders pay the carrier's calculated shipping rate.",
      },
      {
        es: "Los pedidos de más de $750 tienen envío nacional gratis dentro de México.",
        en: "Orders over $750 ship free within Mexico.",
      },
    ] as Bi[],
  },
  form: {
    title: { es: "Solicitud de cuenta de mayoreo", en: "Wholesale account application" },
    business: { es: "Nombre del negocio", en: "Business name" },
    contact: { es: "Correo de contacto", en: "Contact email" },
    country: { es: "País", en: "Country" },
    tier: { es: "Nivel que te interesa", en: "Tier you're interested in" },
    license: { es: "Número de licencia o certificado de reventa", en: "Business license or resale certificate number" },
    message: { es: "Cuéntanos de tu tienda (opcional)", en: "Tell us about your shop (optional)" },
    submit: { es: "Enviar solicitud", en: "Send application" },
  },
};

/* -------------------------------------------------------------------- help */

/** Shipping & Returns Policy, effective February 1, 2026. */
export const HELP = {
  eyebrow: { es: "Ayuda", en: "Help" },
  title: { es: "Envíos, devoluciones y preguntas", en: "Shipping, returns and questions" },
  lede: {
    es: "Política vigente desde el 1 de febrero de 2026, para pedidos de menudeo y mayoreo.",
    en: "Policy in effect since February 1, 2026, for retail and wholesale orders.",
  },
  jump: { es: "Ir a", en: "Jump to" },
  shipping: {
    title: { es: "Envíos", en: "Shipping" },
    zone: { es: "Zona", en: "Zone" },
    carrier: { es: "Paquetería", en: "Carrier" },
    transit: { es: "Tránsito típico", en: "Typical transit" },
    zones: [
      { zone: { es: "México (nacional)", en: "Mexico (domestic)" }, carrier: "Estafeta", transit: { es: "2–4 días hábiles", en: "2–4 business days" } },
      { zone: { es: "Estados Unidos y Canadá", en: "United States & Canada" }, carrier: "DHL Express", transit: { es: "5–8 días hábiles", en: "5–8 business days" } },
      { zone: { es: "Resto de Latinoamérica", en: "Rest of Latin America" }, carrier: "DHL Express", transit: { es: "6–10 días hábiles", en: "6–10 business days" } },
      { zone: { es: "Europa (solo algunas cuentas de mayoreo)", en: "Europe (select wholesale only)" }, carrier: "FedEx International", transit: { es: "8–12 días hábiles", en: "8–12 business days" } },
    ],
    costsTitle: { es: "Costo de envío", en: "Shipping costs" },
    costs: [
      { es: "Menudeo de menos de $50: $6.50 nacional, $18 internacional.", en: "Retail under $50: flat $6.50 domestic, $18 international." },
      { es: "Menudeo de $50 o más: envío nacional gratis y 50 % de descuento en el internacional.", en: "Retail $50 and up: free domestic shipping, and 50% off international shipping." },
      { es: "Mayoreo: se calcula al pagar, por peso y destino. Más de $750, envío nacional gratis.", en: "Wholesale: calculated at checkout by weight and destination. Over $750 ships free domestically." },
    ] as Bi[],
    processingTitle: { es: "Tiempo de preparación", en: "Processing time" },
    order: { es: "Tipo de pedido", en: "Order type" },
    processing: { es: "Preparación", en: "Processing" },
    processingRows: [
      { order: { es: "Menudeo / aficionados", en: "Retail / hobbyist" }, time: { es: "1–3 días hábiles", en: "1–3 business days" } },
      { order: { es: "Tiendas (mayoreo)", en: "Boutique wholesale" }, time: { es: "5–7 días hábiles", en: "5–7 business days" } },
      { order: { es: "Mayoristas y distribuidores", en: "Large wholesale / distributor" }, time: { es: "10–14 días hábiles", en: "10–14 business days" } },
      { order: { es: "Colores a la medida", en: "Custom color orders" }, time: { es: "15–20 días hábiles, después de aprobar el color", en: "15–20 business days, after color approval" } },
    ],
    cutoff: {
      es: "La preparación no incluye el tránsito. Los pedidos hechos después de las 2:00 p. m. (hora local) se preparan el siguiente día hábil.",
      en: "Processing time doesn't include transit. Orders placed after 2:00 PM local time are processed the next business day.",
    },
    customs: {
      es: "En pedidos internacionales, los aranceles, impuestos de importación y gastos de agencia corren por cuenta del cliente. No los prepagamos ni los reembolsamos.",
      en: "On international orders, customs duties, import taxes and brokerage fees are the customer's responsibility. We don't prepay or refund them.",
    },
  },
  returns: {
    title: { es: "Devoluciones", en: "Returns" },
    yesTitle: { es: "Se pueden devolver", en: "Can be returned" },
    yes: [
      { es: "Cuentas y dijes sin usar y sin abrir, en su empaque original.", en: "Unused, unopened beads and charms, in their original packaging." },
      { es: "Dentro de los 30 días posteriores a la entrega.", en: "Within 30 days of delivery." },
      { es: "Con tu recibo o número de pedido.", en: "With your receipt or order number." },
    ] as Bi[],
    noTitle: { es: "No se pueden devolver", en: "Can't be returned" },
    no: [
      { es: "Pedidos de color a la medida.", en: "Custom color orders." },
      { es: "Artículos de liquidación o de Scrap Bin.", en: "Clearance and Scrap Bin items." },
      { es: "Avíos abiertos (broches, argollas, hilo) una vez roto el sello, por higiene y control de calidad.", en: "Opened findings (clasps, jump rings, wire) once the seal is broken, for hygiene and quality control." },
    ] as Bi[],
    howTitle: { es: "Cómo iniciar una devolución", en: "How to start a return" },
    how: [
      { es: "Escribe a support@hildaluna-sample.com con tu número de pedido.", en: "Email support@hildaluna-sample.com with your order number." },
      { es: "En pedidos nacionales te mandamos una guía prepagada en 2 días hábiles.", en: "For domestic orders, we send a prepaid return label within 2 business days." },
      { es: "Reembolsamos a tu método de pago original en 5 días hábiles después de recibir el artículo.", en: "We refund your original payment method within 5 business days of receiving the item." },
    ] as Bi[],
  },
  damage: {
    title: { es: "Artículos dañados o equivocados", en: "Damaged or wrong items" },
    items: [
      { es: "Avísanos dentro de los 7 días posteriores a la entrega, con fotos.", en: "Tell us within 7 days of delivery, with photos." },
      { es: "Si se rompieron menos de 20 piezas, las reponemos sin que tengas que devolverlas.", en: "If fewer than 20 pieces broke, we replace them with no return needed." },
      { es: "Con 20 piezas o más, quizá pidamos las piezas dañadas para el reclamo a la paquetería; te mandamos una guía prepagada.", en: "With 20 pieces or more, we may ask for the damaged items back for the carrier claim; we'll send a prepaid label." },
    ] as Bi[],
  },
  changes: {
    title: { es: "Cambios y cancelaciones", en: "Changes and cancellations" },
    body: {
      es: "Puedes cambiar o cancelar tu pedido sin costo antes de que entre a preparación. Cuando aparece como \"En preparación\", ya no podemos garantizar cambios, porque quizá ya empezamos a surtirlo.",
      en: "You can change or cancel an order at no charge before it enters processing. Once it shows \"Processing\", we can't promise changes, since picking may have started.",
    },
  },
  faq: { title: { es: "Preguntas frecuentes", en: "Frequently asked questions" } },
  contact: {
    title: { es: "¿Necesitas algo más?", en: "Need anything else?" },
    body: {
      es: "Escríbenos y te respondemos en un máximo de 2 días hábiles.",
      en: "Write to us and we'll reply within 2 business days.",
    },
    name: { es: "Tu nombre", en: "Your name" },
    email: { es: "Tu correo", en: "Your email" },
    order: { es: "Número de pedido (opcional)", en: "Order number (optional)" },
    message: { es: "¿En qué te ayudamos?", en: "How can we help?" },
    submit: { es: "Enviar mensaje", en: "Send message" },
  },
};

/** Customer FAQ, in the document's order. */
export const FAQ: { group: Bi; items: { q: Bi; a: Bi }[] }[] = [
  {
    group: { es: "Pedidos", en: "Ordering" },
    items: [
      {
        q: { es: "¿Cuál es el pedido mínimo para precio de mayoreo?", en: "What is the minimum order for wholesale pricing?" },
        a: {
          es: "Las tiendas necesitan un pedido mínimo de $150, y los mayoristas o distribuidores, de $750. Los pedidos de menudeo no tienen mínimo.",
          en: "Boutique wholesale needs a $150 minimum order, and large wholesale or distributor pricing a $750 minimum. Retail orders have no minimum.",
        },
      },
      {
        q: { es: "¿Cuánto tarda en salir un pedido?", en: "How long does an order take to ship?" },
        a: {
          es: "Menudeo: 1 a 3 días hábiles. Tiendas: 5 a 7 días hábiles. Mayoristas y distribuidores: 10 a 14 días hábiles.",
          en: "Retail: 1 to 3 business days. Boutique wholesale: 5 to 7 business days. Large wholesale and distributors: 10 to 14 business days.",
        },
      },
      {
        q: { es: "¿Pueden hacer un color de cuenta a la medida?", en: "Can I get a custom bead color made?" },
        a: {
          es: "Evaluamos cada caso; en general se pide un mínimo de 2 kg de vidrio por color. Escribe a wholesale@hildaluna-sample.com para pedir una cotización.",
          en: "We look at each request case by case; it generally needs at least 2 kg of glass per color. Write to wholesale@hildaluna-sample.com for a quote.",
        },
      },
    ],
  },
  {
    group: { es: "Envíos y devoluciones", en: "Shipping & returns" },
    items: [
      {
        q: { es: "¿Hacen envíos internacionales?", en: "Do you ship internationally?" },
        a: {
          es: "Sí, a Estados Unidos, Canadá y casi toda Latinoamérica. Los aranceles corren por cuenta del cliente.",
          en: "Yes, to the United States, Canada and most of Latin America. Customs duties are the customer's responsibility.",
        },
      },
      {
        q: { es: "¿Cuál es su política de devoluciones?", en: "What is your return policy?" },
        a: {
          es: "Las cuentas y dijes sin usar y sin abrir se pueden devolver dentro de 30 días para un reembolso completo. Los colores a la medida y los artículos de liquidación o Scrap Bin no tienen devolución.",
          en: "Unused, unopened beads and charms can be returned within 30 days of delivery for a full refund. Custom colors and clearance or Scrap Bin items are final sale.",
        },
      },
      {
        q: { es: "Mi pedido llegó con cuentas rotas. ¿Qué hago?", en: "My order arrived with broken beads. What do I do?" },
        a: {
          es: "Escríbenos dentro de 7 días con fotos del daño. Reponemos las piezas sin costo; si son menos de 20, no tienes que devolverlas.",
          en: "Contact us within 7 days of delivery with photos. We replace the items at no charge, and for fewer than 20 pieces you don't need to send anything back.",
        },
      },
    ],
  },
  {
    group: { es: "Productos", en: "Products" },
    items: [
      {
        q: { es: "¿Sus cuentas y dijes son libres de níquel?", en: "Are your beads and charms nickel-free?" },
        a: {
          es: "Todos los dijes son de peltre sin plomo. Los acabados de oro y rodio no tienen níquel; el bronce antiguo tiene trazas, así que si tienes sensibilidad elige oro o rodio.",
          en: "All charms are cast in lead-free pewter. Gold plate and rhodium finishes are nickel-free; antique bronze has trace nickel, so choose gold or rhodium if you're sensitive.",
        },
      },
      {
        q: { es: "¿Qué diferencia hay entre Coastal Garden y Amber Hollow?", en: "What's the difference between Coastal Garden and Amber Hollow?" },
        a: {
          es: "Coastal Garden (primavera-verano) tiene cuentas pastel con dijes botánicos y de conchas. Amber Hollow (otoño-invierno) tiene tonos ámbar, óxido y verde bosque con dijes de bellota, luna y hongo.",
          en: "Coastal Garden (Spring/Summer) has pastel glass beads with botanical and seashell charms. Amber Hollow (Fall/Winter) has warm amber, rust and forest-green tones with acorn, moon and mushroom charms.",
        },
      },
      {
        q: { es: "¿Venden avíos (broches, argollas, hilo) por separado?", en: "Do you sell findings (clasps, jump rings, wire) separately?" },
        a: {
          es: "Sí, se venden por separado y no se incluyen en el precio de cuentas o dijes, salvo que vengan en un kit.",
          en: "Yes, findings are sold individually and aren't included in bead or charm prices unless they're part of a kit.",
        },
      },
    ],
  },
  {
    group: { es: "Cuentas y mayoreo", en: "Accounts & wholesale" },
    items: [
      {
        q: { es: "¿Cómo solicito una cuenta de mayoreo?", en: "How do I apply for a wholesale account?" },
        a: {
          es: "Envía la solicitud en este sitio con tu licencia comercial o certificado de reventa. La aprobación suele tardar de 3 a 5 días hábiles.",
          en: "Send an application on this site with your business license or resale certificate. Approval usually takes 3 to 5 business days.",
        },
      },
      {
        q: { es: "¿Tienen programa de lealtad o recompensas?", en: "Do you have a loyalty or rewards program?" },
        a: {
          es: "Por ahora no, pero quienes están en nuestra lista de correo se enteran primero de las ventas de Scrap Bin y de los colores de edición limitada.",
          en: "Not yet, but people on our email list hear first about Scrap Bin sales and limited-release colorways.",
        },
      },
    ],
  },
];

/* ------------------------------------------------------------ staff sign-in */

export const STAFF = {
  eyebrow: { es: "Solo personal", en: "Staff only" },
  title: { es: "Acceso a la intranet", en: "Intranet sign-in" },
  body: {
    es: "Políticas, horarios, avisos y Luna, la asistente que responde con los documentos internos.",
    en: "Policies, schedules, notices, and Luna, the assistant who answers from the internal documents.",
  },
  simulated: { es: "Acceso simulado", en: "Simulated sign-in" },
  simulatedBody: {
    es: "Esta demo no tiene cuentas ni contraseñas. Cualquiera que pueda abrir este servidor puede entrar a la intranet.",
    en: "This demo has no accounts or passwords. Anyone who can reach this server can open the intranet.",
  },
  enter: { es: "Entrar como empleado de demostración", en: "Enter as demo employee" },
  back: { es: "Volver al sitio", en: "Back to the website" },
};

/* -------------------------------------------------------------- demo forms */

export const DEMO_FORM = {
  sent: {
    es: "Sitio de demostración: no se envió nada y no se guardó ningún dato.",
    en: "Demo site: nothing was sent and nothing was stored.",
  },
};
