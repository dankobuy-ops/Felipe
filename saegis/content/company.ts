export const company = {
  name: "Seguros Aegis",
  legalName: "Seguros Aegis",
  tagline: "Te protegemos a ti, tu familia y tus inversiones.",
  descriptionShort:
    "Corredora de seguros con más de 40 años de experiencia asesorando a personas, empresas y comunidades en Chile.",
  phone: "+56 9 3928 1773",
  phoneHref: "tel:+56939281773",
  whatsappHref: "https://wa.me/56939281773",
  email: "contacto@segurosaegis.cl",
  emailHref: "mailto:contacto@segurosaegis.cl",
  address: {
    street: "Antonio Bellet",
    city: "Providencia",
    region: "Santiago",
    country: "Chile",
    countryCode: "CL",
  },
  schedule: "Lunes a viernes · 9:00 a 18:00 hrs",
  yearsExperience: 40,
  insurers: 12,
  regulators: ["CMF — Comisión para el Mercado Financiero", "ANS — Asociación Nacional de Seguros"],
  googleFormUrl:
    "https://docs.google.com/forms/d/e/1FAIpQLScKoDzINjkyCJzsi05Hr4ZJmN3g8yDOLOcKX7n6t5quPzCtmA/viewform?embedded=true",
  googleFormUrlShare: "https://forms.gle/bmGtgTQ2E7eTiYPd7",
  url: "https://segurosaegis.cl",
  stats: [
    { label: "años de experiencia", value: "40+" },
    { label: "aseguradoras asociadas", value: "12" },
    { label: "áreas cubiertas", value: "Personas, Empresas y Comunidades" },
    { label: "respaldo regulatorio", value: "CMF & ANS" },
  ],
} as const;

export type Company = typeof company;
