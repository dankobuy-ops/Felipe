import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Container } from "@/components/ui/container";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CoverageList } from "@/components/marketing/CoverageList";
import type { Product } from "@/types/product";

export function ProductDetail({ product }: { product: Product }) {
  const Icon = product.icon;
  return (
    <>
      <section className="relative overflow-hidden bg-primary text-primary-foreground">
        <Container className="relative py-16 md:py-24">
          <nav
            aria-label="Breadcrumb"
            className="mb-8 flex items-center gap-1.5 text-xs text-primary-foreground/60"
          >
            <Link href="/" className="hover:text-accent">Inicio</Link>
            <ChevronRight className="size-3" />
            <Link href="/personas" className="hover:text-accent">Personas</Link>
            <ChevronRight className="size-3" />
            <span className="text-primary-foreground/90">{product.title}</span>
          </nav>
          <div className="grid items-start gap-10 md:grid-cols-[auto_1fr] md:gap-12">
            <span className="inline-flex size-16 items-center justify-center rounded-2xl bg-accent/15 text-accent">
              <Icon className="size-7" />
            </span>
            <div className="space-y-5">
              {product.tag && (
                <Badge
                  variant="accent"
                  className="uppercase tracking-wider"
                >
                  {product.tag}
                </Badge>
              )}
              <h1 className="font-display text-4xl leading-[1.05] sm:text-5xl">
                {product.title}
              </h1>
              <p className="max-w-2xl text-lg leading-relaxed text-primary-foreground/80">
                {product.longDescription}
              </p>
              <div className="flex flex-wrap gap-3 pt-2">
                <Button asChild variant="accent" size="lg">
                  <Link href="/contacto">Cotizar {product.title.toLowerCase()}</Link>
                </Button>
                <Button
                  asChild
                  size="lg"
                  variant="outline"
                  className="border-primary-foreground/25 bg-transparent text-primary-foreground hover:bg-primary-foreground/10"
                >
                  <Link href="/personas">Ver todos los seguros</Link>
                </Button>
              </div>
            </div>
          </div>
        </Container>
      </section>

      <section className="section-y">
        <Container>
          <div className="mx-auto max-w-2xl text-center">
            <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
              Coberturas incluidas
            </p>
            <h2 className="font-display text-3xl text-foreground sm:text-4xl">
              Lo que cubre tu {product.title.toLowerCase()}.
            </h2>
            <p className="mt-4 text-muted-foreground">
              Las coberturas específicas se adaptan al plan y aseguradora que elijas. Te guiamos para que entiendas cada detalle.
            </p>
          </div>
          <div className="mt-12">
            <CoverageList coverages={product.coverages} variant="list" />
          </div>
        </Container>
      </section>
    </>
  );
}
