import Link from "next/link";
import { ArrowUpRight, Users, Building2, Home } from "lucide-react";
import { Container } from "@/components/ui/container";

const categories = [
  {
    title: "Personas",
    description:
      "Auto, hogar, salud, viajes, deportivo, responsabilidad civil y más. Diseñamos el plan correcto para ti y tu familia.",
    href: "/personas",
    icon: Users,
    bullets: ["Vehicular", "Hogar", "Salud complementaria", "Asistencia en viajes"],
  },
  {
    title: "Empresas",
    description:
      "Programas integrales que protegen tu operación, tu gente y tus activos más críticos.",
    href: "/empresas",
    icon: Building2,
    bullets: ["Incendio y adicionales", "Responsabilidad civil", "Transporte de carga", "Vida colectivo"],
  },
  {
    title: "Comunidades",
    description:
      "Pólizas especializadas para edificios y condominios, con coberturas para áreas comunes y residentes.",
    href: "/comunidades",
    icon: Home,
    bullets: ["Incendio edificio", "Espacios comunes", "RC de la comunidad", "Accidentes personales"],
  },
];

export function CategoryGrid() {
  return (
    <section className="section-y">
      <Container>
        <div className="mx-auto max-w-2xl text-center">
          <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
            A quién asesoramos
          </p>
          <h2 className="font-display text-3xl text-foreground sm:text-4xl">
            Protección diseñada a tu medida.
          </h2>
        </div>
        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {categories.map(({ title, description, href, icon: Icon, bullets }) => (
            <Link
              key={href}
              href={href}
              className="group flex flex-col rounded-2xl border border-border bg-background p-7 shadow-[var(--shadow-card)] transition-all hover:-translate-y-1 hover:border-primary/30 hover:shadow-[var(--shadow-card-hover)]"
            >
              <div className="flex items-start justify-between gap-4">
                <span className="inline-flex size-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
                  <Icon className="size-5" />
                </span>
                <ArrowUpRight className="size-5 -translate-y-0.5 translate-x-0.5 text-muted-foreground transition-all group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-primary" />
              </div>
              <h3 className="mt-6 font-display text-2xl text-foreground">
                {title}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {description}
              </p>
              <ul className="mt-6 space-y-1.5 text-sm text-foreground/80">
                {bullets.map((b) => (
                  <li key={b} className="flex items-center gap-2">
                    <span className="size-1 rounded-full bg-accent" />
                    {b}
                  </li>
                ))}
              </ul>
              <span className="mt-6 inline-flex items-center gap-1 text-sm font-medium text-primary">
                Ver cobertura
                <span className="transition-transform group-hover:translate-x-0.5">→</span>
              </span>
            </Link>
          ))}
        </div>
      </Container>
    </section>
  );
}
