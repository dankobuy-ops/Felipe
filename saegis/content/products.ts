import {
  Plane,
  Bike,
  HeartPulse,
  Trophy,
  Home,
  Accessibility,
  Globe2,
  Stethoscope,
  Shield,
  Briefcase,
  Car,
} from "lucide-react";
import type { Product } from "@/types/product";

export const products: Product[] = [
  {
    slug: "vehiculo",
    title: "Seguro Vehicular",
    shortDescription:
      "Cobertura integral para tu auto: daño material, robo, responsabilidad civil y asistencia en ruta.",
    longDescription:
      "Protege tu vehículo ante daños, robo y responsabilidades frente a terceros con planes que se adaptan al uso y valor de tu auto. Incluye asistencia en ruta, auto de reemplazo y cobertura para conductores designados.",
    icon: Car,
    audience: "personas",
    featured: true,
    tag: "Más solicitado",
    coverages: [
      { title: "Daño material", description: "Colisión, choque, volcadura, incendio y rayo." },
      { title: "Robo y uso no autorizado", description: "Indemnización si el vehículo no se recupera en 30 días." },
      { title: "Responsabilidad civil", description: "Cobertura de daños y lesiones a terceros." },
      { title: "Accesorios", description: "Protección para equipos desmontables declarados." },
      { title: "Fenómenos de la naturaleza", description: "Sismo, granizo, inundación, viento y aluvión." },
      { title: "Defensa legal", description: "Honorarios de abogados y gastos de fianza." },
      { title: "Pasajeros", description: "Indemnización por muerte o invalidez de ocupantes." },
      { title: "Asistencia en ruta", description: "Grúa, auto de reemplazo y conductor sustituto según plan.", highlighted: true },
    ],
  },
  {
    slug: "hogar",
    title: "Seguro Hogar",
    shortDescription:
      "Tranquilidad para tu casa o departamento ante incendio, sismo, robo y daños por agua.",
    longDescription:
      "Un plan integral para proteger tu vivienda y tus bienes frente a los riesgos más frecuentes en Chile: sismos, incendios, robos y daños por filtración. Incluye asistencia de emergencia 24/7.",
    icon: Home,
    audience: "personas",
    featured: true,
    coverages: [
      { title: "Incendio", description: "Incluye daños por humo, calor y agua de los bomberos." },
      { title: "Sismo", description: "Cobertura opcional — altamente recomendada en Chile.", highlighted: true },
      { title: "Fenómenos de la naturaleza", description: "Viento, lluvia, inundación, granizo, aluvión." },
      { title: "Daño por agua", description: "Rotura de cañerías — la cobertura opcional más usada.", optional: true, highlighted: true },
      { title: "Robo con fuerza", description: "Sustracción de bienes con evidencia de forzamiento.", optional: true },
      { title: "Responsabilidad civil familiar", description: "Daños causados por integrantes del hogar o mascotas.", optional: true },
      { title: "Daños eléctricos", description: "Sobretensiones que afecten aparatos eléctricos.", optional: true },
      { title: "Gastos extraordinarios", description: "Alojamiento temporal y bodegaje si la vivienda queda inhabitable.", optional: true },
    ],
  },
  {
    slug: "salud",
    title: "Seguro de Salud Complementario",
    shortDescription:
      "Reembolso de copagos y gastos médicos complementarios a tu Isapre o Fonasa.",
    longDescription:
      "Refuerza tu plan de salud cubriendo el 60% a 80% del copago en hospitalizaciones, consultas, exámenes y medicamentos. Flexible, escalable y adaptable a familias completas.",
    icon: Stethoscope,
    audience: "personas",
    featured: true,
    coverages: [
      { title: "Hospitalización", description: "Cobertura del copago en hospitalización médica y quirúrgica." },
      { title: "Atención ambulatoria", description: "Consultas, exámenes, procedimientos y medicamentos." },
      { title: "Maternidad", description: "Controles prenatales, parto y hospitalización del recién nacido.", optional: true },
      { title: "Dental", description: "Coberturas básicas y tratamientos especializados.", optional: true },
      { title: "Enfermedades graves", description: "Beneficios adicionales por diagnóstico de patologías críticas.", optional: true },
    ],
  },
  {
    slug: "catastrofico",
    title: "Seguro Catastrófico",
    shortDescription:
      "Cobertura hasta UF 20.000 para enfermedades graves o accidentes de alto costo.",
    longDescription:
      "Un respaldo económico en caso de enfermedades o accidentes de alto costo que superan el alcance de tu plan de salud base.",
    icon: HeartPulse,
    audience: "personas",
    coverages: [
      { title: "Cobertura hasta UF 20.000", description: "Tope elevado para gastos hospitalarios catastróficos." },
      { title: "Hospitalización prolongada", description: "Pabellones, días cama, insumos y equipos de alta complejidad." },
      { title: "Tratamientos oncológicos", description: "Quimioterapia, radioterapia y medicamentos oncológicos." },
      { title: "Trasplantes", description: "Procedimientos y tratamientos inmunosupresores." },
    ],
  },
  {
    slug: "asistencia-viajes",
    title: "Asistencia en Viajes",
    shortDescription:
      "Apoyo médico, legal y logístico mientras estás fuera de Chile.",
    longDescription:
      "Viaja con tranquilidad con asistencia médica internacional, cobertura por cancelación, pérdida de equipaje y soporte 24/7 en español.",
    icon: Plane,
    audience: "personas",
    coverages: [
      { title: "Gastos médicos internacionales", description: "Atención de urgencia, hospitalización y medicamentos." },
      { title: "Equipaje", description: "Pérdida, demora o daño de maletas." },
      { title: "Cancelación de viaje", description: "Reembolso ante imprevistos de salud o familiares." },
      { title: "Asistencia legal", description: "Soporte ante incidentes legales en el extranjero." },
    ],
  },
  {
    slug: "bicicleta",
    title: "Seguro Bicicleta",
    shortDescription:
      "Cobertura hasta UF 100 ante robo, accidentes y responsabilidad civil.",
    longDescription:
      "Protege tu bicicleta urbana, MTB o de ruta ante robo con fuerza, daños accidentales y responsabilidad civil por lesiones a terceros.",
    icon: Bike,
    audience: "personas",
    coverages: [
      { title: "Robo con fuerza", description: "Indemnización por hurto con evidencia de forzamiento." },
      { title: "Daño accidental", description: "Reparación o reposición por siniestros." },
      { title: "Responsabilidad civil", description: "Daños a terceros durante el uso." },
      { title: "Accidentes personales", description: "Indemnización por lesiones del ciclista." },
    ],
  },
  {
    slug: "deporte",
    title: "Seguro Deportivo",
    shortDescription:
      "Protección ante lesiones y accidentes practicando deportes.",
    longDescription:
      "Diseñado para deportistas recreativos y federados: cubre gastos médicos, días de incapacidad e invalidez por accidentes deportivos.",
    icon: Trophy,
    audience: "personas",
    coverages: [
      { title: "Gastos médicos por accidente", description: "Consultas, exámenes, hospitalización y rehabilitación." },
      { title: "Invalidez accidental", description: "Indemnización por invalidez total o parcial." },
      { title: "Días de incapacidad", description: "Compensación diaria durante la recuperación." },
      { title: "Muerte accidental", description: "Beneficio a los beneficiarios designados." },
    ],
  },
  {
    slug: "movilidad",
    title: "Seguro de Movilidad",
    shortDescription:
      "Protección diaria ante accidentes personales en la vía pública.",
    longDescription:
      "Cobertura orientada a peatones y usuarios de transporte que sufren lesiones por accidentes fuera del hogar.",
    icon: Accessibility,
    audience: "personas",
    coverages: [
      { title: "Accidentes personales", description: "Indemnización por lesiones en la vía pública." },
      { title: "Gastos médicos", description: "Atención de urgencia y rehabilitación." },
      { title: "Indemnización por invalidez", description: "Pago único según grado de invalidez." },
    ],
  },
  {
    slug: "rci",
    title: "RC Vehicular Mercosur (RCI)",
    shortDescription:
      "Responsabilidad civil obligatoria para cruzar a países del Mercosur.",
    longDescription:
      "Cumple con la normativa para circular en Argentina, Uruguay, Paraguay, Brasil y Bolivia con coberturas desde USD 20.000 hasta USD 40.000.",
    icon: Globe2,
    audience: "personas",
    coverages: [
      { title: "Cobertura USD 20.000 a 40.000", description: "Según país y plan contratado." },
      { title: "Daños materiales a terceros", description: "Indemnización por daños causados a otros vehículos o bienes." },
      { title: "Lesiones y muerte a terceros", description: "Cobertura por daños personales." },
      { title: "Homologado Mercosur", description: "Válido en pasos fronterizos oficiales." },
    ],
  },
  {
    slug: "rc-medica",
    title: "RC Médica",
    shortDescription:
      "Responsabilidad civil profesional para médicos y personal clínico.",
    longDescription:
      "Protección legal y económica frente a demandas por negligencia médica. Incluye defensa jurídica y costos de indemnización.",
    icon: Stethoscope,
    audience: "personas",
    coverages: [
      { title: "Responsabilidad civil profesional", description: "Indemnizaciones por errores o negligencias médicas." },
      { title: "Defensa legal", description: "Honorarios de abogados y gastos judiciales." },
      { title: "Gastos administrativos", description: "Costos de peritajes y documentación técnica." },
    ],
  },
  {
    slug: "rc-personal",
    title: "RC Personal",
    shortDescription:
      "Cobertura por daños involuntarios causados a terceros.",
    longDescription:
      "Pensado para personas y familias: protege ante reclamos por daños materiales o lesiones causados de forma accidental.",
    icon: Shield,
    audience: "personas",
    coverages: [
      { title: "Daños a terceros", description: "Bienes dañados accidentalmente." },
      { title: "Lesiones a terceros", description: "Gastos médicos y compensaciones." },
      { title: "Defensa legal", description: "Asesoría jurídica en caso de demanda." },
    ],
  },
  {
    slug: "rc-profesional",
    title: "RC Profesional",
    shortDescription:
      "Protección frente a demandas por errores u omisiones profesionales.",
    longDescription:
      "Para consultores, ingenieros, arquitectos, abogados, contadores y otros profesionales independientes que necesitan respaldo ante riesgos de su ejercicio.",
    icon: Briefcase,
    audience: "personas",
    coverages: [
      { title: "Errores u omisiones", description: "Indemnización por fallas profesionales." },
      { title: "Defensa legal", description: "Honorarios y gastos procesales." },
      { title: "Pérdida de documentos", description: "Gastos de reposición y reconstrucción." },
    ],
  },
];

export const productsBySlug = new Map<string, Product>(
  products.map((p) => [p.slug, p]),
);

export const featuredProducts = products.filter((p) => p.featured);

export const personaProducts = products.filter((p) => p.audience === "personas");
