import type { Coverage } from "@/types/product";

export interface BusinessCoverage extends Coverage {
  slug: string;
}

export const businessCoverages: BusinessCoverage[] = [
  {
    slug: "incendio-y-adicionales",
    title: "Incendio y adicionales",
    description:
      "Protege instalaciones, maquinarias y mercaderías ante incendio, sismo, fenómenos de la naturaleza y daños por agua.",
  },
  {
    slug: "responsabilidad-civil",
    title: "Responsabilidad Civil Empresarial",
    description:
      "Cobertura ante daños a terceros derivados de la actividad operacional, productos y servicios de la empresa.",
  },
  {
    slug: "transporte-y-carga",
    title: "Transporte de Carga",
    description:
      "Protección de mercaderías en tránsito terrestre, marítimo o aéreo, nacional e internacional.",
  },
  {
    slug: "equipos-electronicos",
    title: "Equipos Electrónicos y Maquinaria",
    description:
      "Cubre averías, daños accidentales y robo de equipos críticos para la operación.",
  },
  {
    slug: "vida-colectivo",
    title: "Vida y Salud Colectivos",
    description:
      "Planes corporativos para equipos: seguro de vida, salud complementario y accidentes del trabajo.",
  },
  {
    slug: "perjuicio-por-paralizacion",
    title: "Perjuicio por Paralización",
    description:
      "Indemniza la utilidad bruta y los gastos fijos cuando un siniestro detiene la operación.",
  },
  {
    slug: "directores-y-ejecutivos",
    title: "D&O — Directores y Ejecutivos",
    description:
      "Protege el patrimonio personal de directores y ejecutivos ante reclamos por su gestión.",
  },
  {
    slug: "fidelidad-funcionaria",
    title: "Fidelidad Funcionaria",
    description:
      "Cobertura ante fraudes internos cometidos por empleados de confianza.",
  },
  {
    slug: "caucion-y-garantia",
    title: "Garantía y Caución",
    description:
      "Pólizas de fiel cumplimiento, seriedad de oferta y anticipos para licitaciones y contratos.",
  },
];

export const businessPillars = [
  {
    title: "Diagnóstico del riesgo",
    description:
      "Visitamos tu operación, identificamos exposiciones críticas y construimos un mapa de riesgos a medida.",
  },
  {
    title: "Diseño de programa",
    description:
      "Armamos un portafolio con deducibles, coberturas y aseguradoras que equilibran protección y costo.",
  },
  {
    title: "Gestión continua",
    description:
      "Acompañamos renovaciones, siniestros y crecimientos del negocio como un socio estratégico a largo plazo.",
  },
];
