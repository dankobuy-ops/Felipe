import { Hero } from "@/components/marketing/Hero";
import { ValueProps } from "@/components/marketing/ValueProps";
import { CategoryGrid } from "@/components/marketing/CategoryGrid";
import { PartnersStrip } from "@/components/marketing/PartnersStrip";
import { Testimonials } from "@/components/marketing/Testimonials";
import { CTA } from "@/components/marketing/CTA";
import { ProductCard } from "@/components/marketing/ProductCard";
import { Container } from "@/components/ui/container";
import { featuredProducts } from "@/content/products";

export default function HomePage() {
  return (
    <>
      <Hero />
      <ValueProps />
      <CategoryGrid />

      <section className="section-y bg-surface">
        <Container>
          <div className="mx-auto max-w-2xl text-center">
            <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
              Productos destacados
            </p>
            <h2 className="font-display text-3xl text-foreground sm:text-4xl">
              Los seguros que más nos solicitan.
            </h2>
            <p className="mt-4 text-muted-foreground">
              Una muestra de nuestro portafolio para personas. Todas las coberturas se ajustan a tu contexto real.
            </p>
          </div>
          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {featuredProducts.map((p) => (
              <ProductCard key={p.slug} product={p} />
            ))}
          </div>
        </Container>
      </section>

      <PartnersStrip />
      <Testimonials />
      <CTA />
    </>
  );
}
