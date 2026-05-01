import { Container } from "@/components/ui/container";
import { ProductCard } from "@/components/marketing/ProductCard";
import { PartnersStrip } from "@/components/marketing/PartnersStrip";
import { CTA } from "@/components/marketing/CTA";
import { personaProducts } from "@/content/products";
import { buildMetadata } from "@/lib/seo";

export const metadata = buildMetadata({
  title: "Seguros para Personas",
  description:
    "Seguros vehiculares, hogar, salud, viajes, bicicleta, deportivo y responsabilidad civil. Asesoría independiente para ti y tu familia.",
  path: "/personas",
});

export default function PersonasPage() {
  return (
    <>
      <section className="bg-primary text-primary-foreground">
        <Container className="py-20 md:py-28">
          <div className="max-w-3xl space-y-6">
            <p className="text-sm uppercase tracking-wider text-primary-foreground/60">
              Personas
            </p>
            <h1 className="font-display text-4xl leading-[1.05] sm:text-5xl md:text-6xl">
              Protección pensada para{" "}
              <span className="text-accent">tu día a día</span>.
            </h1>
            <p className="max-w-2xl text-lg leading-relaxed text-primary-foreground/80">
              Coberturas flexibles que acompañan cada etapa de tu vida. Explora nuestro portafolio y conversemos sobre el plan que mejor se adapta a ti.
            </p>
          </div>
        </Container>
      </section>

      <section className="section-y">
        <Container>
          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {personaProducts.map((p) => (
              <li key={p.slug}>
                <ProductCard product={p} />
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
