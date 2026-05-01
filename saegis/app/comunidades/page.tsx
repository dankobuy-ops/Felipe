import { Container } from "@/components/ui/container";
import { CoverageList } from "@/components/marketing/CoverageList";
import { PartnersStrip } from "@/components/marketing/PartnersStrip";
import { CTA } from "@/components/marketing/CTA";
import { communityCoverages } from "@/content/communities";
import { buildMetadata } from "@/lib/seo";

export const metadata = buildMetadata({
  title: "Seguros para Comunidades",
  description:
    "Pólizas especializadas para edificios y condominios: incendio, espacios comunes, responsabilidad civil, vida guardias y accidentes personales.",
  path: "/comunidades",
});

export default function ComunidadesPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground">
        <Container className="py-20 md:py-28">
          <div className="max-w-3xl space-y-6">
            <p className="text-sm uppercase tracking-wider text-primary-foreground/60">
              Comunidades
            </p>
            <h1 className="font-display text-4xl leading-[1.05] sm:text-5xl md:text-6xl">
              La tranquilidad que tu{" "}
              <span className="text-accent">edificio merece</span>.
            </h1>
            <p className="max-w-2xl text-lg leading-relaxed text-primary-foreground/80">
              Diseñamos pólizas específicas para condominios, edificios residenciales y comunidades: cuidamos la estructura, las áreas comunes, al equipo de trabajo y a cada residente.
            </p>
          </div>
        </Container>
      </section>

      <section className="section-y">
        <Container>
          <div className="mx-auto max-w-2xl text-center">
            <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
              Coberturas de la comunidad
            </p>
            <h2 className="font-display text-3xl text-foreground sm:text-4xl">
              Todo lo que tu edificio necesita proteger.
            </h2>
          </div>
          <div className="mt-12">
            <CoverageList coverages={communityCoverages} />
          </div>
        </Container>
      </section>

      <PartnersStrip />
      <CTA
        title="Asesoramos a comités y administradores"
        description="Coordinemos una reunión con el comité de administración. Preparamos una propuesta clara y comparable entre aseguradoras."
      />
    </>
  );
}
