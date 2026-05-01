import { Container } from "@/components/ui/container";
import { CoverageList } from "@/components/marketing/CoverageList";
import { PartnersStrip } from "@/components/marketing/PartnersStrip";
import { CTA } from "@/components/marketing/CTA";
import { businessCoverages, businessPillars } from "@/content/business";
import { buildMetadata } from "@/lib/seo";

export const metadata = buildMetadata({
  title: "Seguros para Empresas",
  description:
    "Programas integrales de seguros para empresas: incendio, responsabilidad civil, transporte, vida colectivo, D&O y más.",
  path: "/empresas",
});

export default function EmpresasPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground">
        <Container className="py-20 md:py-28">
          <div className="max-w-3xl space-y-6">
            <p className="text-sm uppercase tracking-wider text-primary-foreground/60">
              Empresas
            </p>
            <h1 className="font-display text-4xl leading-[1.05] sm:text-5xl md:text-6xl">
              Protege lo que tu negocio{" "}
              <span className="text-accent">ha construido</span>.
            </h1>
            <p className="max-w-2xl text-lg leading-relaxed text-primary-foreground/80">
              Diseñamos programas de seguros para PyMEs y empresas grandes. Un portafolio que equilibra riesgo, protección y costo, con gestión activa durante todo el año.
            </p>
          </div>
        </Container>
      </section>

      <section className="section-y">
        <Container>
          <div className="mx-auto max-w-2xl text-center">
            <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
              Cómo trabajamos
            </p>
            <h2 className="font-display text-3xl text-foreground sm:text-4xl">
              Un programa a la medida de tu operación.
            </h2>
          </div>
          <ol className="mt-14 grid gap-5 md:grid-cols-3">
            {businessPillars.map((pillar, i) => (
              <li
                key={pillar.title}
                className="rounded-2xl border border-border bg-background p-7 shadow-[var(--shadow-card)]"
              >
                <span className="font-display text-4xl text-accent">
                  0{i + 1}
                </span>
                <h3 className="mt-4 font-display text-xl text-foreground">
                  {pillar.title}
                </h3>
                <p className="mt-2 text-muted-foreground">{pillar.description}</p>
              </li>
            ))}
          </ol>
        </Container>
      </section>

      <section className="section-y bg-surface">
        <Container>
          <div className="mx-auto max-w-2xl text-center">
            <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
              Coberturas para tu empresa
            </p>
            <h2 className="font-display text-3xl text-foreground sm:text-4xl">
              Protección integral del negocio.
            </h2>
            <p className="mt-4 text-muted-foreground">
              Las coberturas se ajustan a tu industria, tamaño y exposiciones específicas. Conversemos sobre el programa que corresponde a tu empresa.
            </p>
          </div>
          <div className="mt-12">
            <CoverageList coverages={businessCoverages} />
          </div>
        </Container>
      </section>

      <PartnersStrip />
      <CTA
        title="Construyamos el programa de tu empresa"
        description="Un asesor senior te contacta para entender tu operación y preparar una propuesta con las aseguradoras correctas."
      />
    </>
  );
}
