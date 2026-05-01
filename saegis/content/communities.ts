import type { Coverage } from "@/types/product";

export interface CommunityCoverage extends Coverage {
  slug: string;
}

export const communityCoverages: CommunityCoverage[] = [
  {
    slug: "incendio-edificio",
    title: "Incendio Edificio",
    description:
      "Cobertura estructural contra incendio, explosión y daños derivados del combate del fuego. Protege la reposición del inmueble común.",
  },
  {
    slug: "incendio-unidades",
    title: "Incendio Unidades",
    description:
      "Protección individual de cada unidad del condominio ante incendios y daños relacionados.",
  },
  {
    slug: "espacios-comunes",
    title: "Espacios Comunes",
    description:
      "Cobertura para jardines, piscinas, quinchos, gimnasios, ascensores y otras áreas compartidas.",
  },
  {
    slug: "responsabilidad-civil",
    title: "Responsabilidad Civil",
    description:
      "Protección ante daños a terceros causados en el edificio o por elementos de la comunidad.",
  },
  {
    slug: "vida-guardias",
    title: "Vida Guardias",
    description:
      "Seguro de vida para el personal de seguridad, conserjería y operaciones del edificio.",
  },
  {
    slug: "accidentes-personales",
    title: "Accidentes Personales",
    description:
      "Cobertura por accidentes sufridos por residentes, personal y visitantes dentro del condominio.",
  },
];
