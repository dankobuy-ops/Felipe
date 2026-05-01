import { Landmark, Users, ShieldCheck, Handshake } from "lucide-react";
import { Container } from "@/components/ui/container";

const values = [
  {
    icon: Landmark,
    title: "40+ años de trayectoria",
    description:
      "Una firma familiar con memoria del mercado y visión de largo plazo.",
  },
  {
    icon: ShieldCheck,
    title: "Regulados por la CMF",
    description:
      "Miembros de la Asociación Nacional de Seguros. Operamos bajo los estándares más exigentes.",
  },
  {
    icon: Users,
    title: "Asesoría personalizada",
    description:
      "Escuchamos, entendemos tu riesgo y diseñamos la cobertura correcta — no plantillas.",
  },
  {
    icon: Handshake,
    title: "Acompañamiento ante siniestros",
    description:
      "Gestionamos denuncias, trámites y reclamos para que tú te enfoques en lo importante.",
  },
];

export function ValueProps() {
  return (
    <section className="section-y bg-surface">
      <Container>
        <div className="mx-auto max-w-2xl text-center">
          <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
            Por qué Seguros Aegis
          </p>
          <h2 className="font-display text-3xl text-foreground sm:text-4xl">
            Más que pólizas. Certeza para tus decisiones.
          </h2>
        </div>
        <ul className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {values.map(({ icon: Icon, title, description }) => (
            <li
              key={title}
              className="group rounded-2xl border border-border bg-background p-6 shadow-[var(--shadow-card)] transition-all hover:-translate-y-0.5 hover:shadow-[var(--shadow-card-hover)]"
            >
              <span className="inline-flex size-11 items-center justify-center rounded-xl bg-primary/5 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                <Icon className="size-5" />
              </span>
              <p className="mt-5 font-display text-lg leading-snug text-foreground">
                {title}
              </p>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {description}
              </p>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
