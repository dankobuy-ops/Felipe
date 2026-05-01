import { ShieldCheck, Handshake, Eye, Scale } from "lucide-react";
import { Container } from "@/components/ui/container";
import { CTA } from "@/components/marketing/CTA";
import { PartnersStrip } from "@/components/marketing/PartnersStrip";
import { TrustBadges } from "@/components/marketing/TrustBadges";
import { buildMetadata } from "@/lib/seo";
import { company } from "@/content/company";

export const metadata = buildMetadata({
  title: "Nosotros",
  description:
    "Seguros Aegis es una corredora familiar con más de 40 años asesorando a clientes en Chile. Conoce nuestra historia, misión y valores.",
  path: "/nosotros",
});

const values = [
  {
    icon: Eye,
    title: "Transparencia",
    description:
      "Explicamos cada cobertura, letra chica incluida. Sin sorpresas al momento de un siniestro.",
  },
  {
    icon: Scale,
    title: "Integridad",
    description:
      "Actuamos con ética inquebrantable. Nuestra recomendación responde a tu interés, no a comisiones.",
  },
  {
    icon: Handshake,
    title: "Compromiso",
    description:
      "Somos socios de largo plazo. Acompañamos renovaciones, siniestros y cambios en tu vida o negocio.",
  },
  {
    icon: ShieldCheck,
    title: "Responsabilidad",
    description:
      "Gestionamos tu patrimonio como si fuera el nuestro. Cada póliza, cada decisión, con total rigor.",
  },
];

const pillars = [
  {
    title: "Asesoría Profesional",
    description:
      "Más que seguros: certeza. Analizamos el mercado para construir coberturas sólidas a un precio justo.",
  },
  {
    title: "Protección Integral",
    description:
      "Planes de seguridad a medida para tu hogar, tu familia y tu negocio. Todas las coberturas bajo un mismo respaldo.",
  },
  {
    title: "Acompañamiento Personal",
    description:
      "Somos tu socio estratégico. Cuidamos tu patrimonio construido con el mismo esmero que lo hiciste tú.",
  },
];

export default function NosotrosPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground">
        <Container className="py-20 md:py-28">
          <div className="max-w-3xl space-y-6">
            <p className="text-sm uppercase tracking-wider text-primary-foreground/60">
              Nosotros
            </p>
            <h1 className="font-display text-4xl leading-[1.05] sm:text-5xl md:text-6xl">
              Una firma familiar con{" "}
              <span className="text-accent">memoria del mercado</span>.
            </h1>
            <p className="max-w-2xl text-lg leading-relaxed text-primary-foreground/80">
              Somos {company.name}, corredora de seguros con más de {company.yearsExperience} años de experiencia. Administramos el patrimonio y la tranquilidad de personas, empresas y comunidades con total claridad y ética.
            </p>
          </div>
        </Container>
      </section>

      <section className="section-y">
        <Container className="grid gap-14 lg:grid-cols-[1fr_1.2fr] lg:items-start">
          <div className="space-y-5">
            <p className="text-sm font-medium uppercase tracking-wider text-muted-foreground">
              Nuestra misión
            </p>
            <h2 className="font-display text-3xl text-foreground sm:text-4xl">
              Un solo lugar para toda tu protección.
            </h2>
            <p className="text-muted-foreground">
              Nuestra misión es entregar a cada cliente un espacio único donde resolver todas sus necesidades de protección — con tranquilidad, cercanía y profesionalismo.
            </p>
            <TrustBadges />
          </div>
          <ul className="grid gap-4">
            {pillars.map((p) => (
              <li
                key={p.title}
                className="rounded-2xl border border-border bg-background p-6 shadow-[var(--shadow-card)]"
              >
                <h3 className="font-display text-xl text-foreground">{p.title}</h3>
                <p className="mt-2 text-muted-foreground">{p.description}</p>
              </li>
            ))}
          </ul>
        </Container>
      </section>

      <section className="section-y bg-surface">
        <Container>
          <div className="mx-auto max-w-2xl text-center">
            <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
              Valores
            </p>
            <h2 className="font-display text-3xl text-foreground sm:text-4xl">
              La forma en que trabajamos.
            </h2>
          </div>
          <ul className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {values.map(({ icon: Icon, title, description }) => (
              <li
                key={title}
                className="rounded-2xl border border-border bg-background p-6"
              >
                <span className="inline-flex size-11 items-center justify-center rounded-xl bg-accent/10 text-accent">
                  <Icon className="size-5" />
                </span>
                <p className="mt-5 font-display text-lg text-foreground">
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

      <PartnersStrip />
      <CTA />
    </>
  );
}
