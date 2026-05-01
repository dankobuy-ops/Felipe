import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Container } from "@/components/ui/container";
import { company } from "@/content/company";

export function CTA({
  title = "¿Listo para cotizar tu seguro?",
  description = "Conversemos. Un asesor te responde el mismo día con propuestas de las principales aseguradoras del país.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <section className="relative overflow-hidden bg-primary text-primary-foreground">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(circle at 85% 0%, oklch(0.72 0.12 75 / 0.2), transparent 55%)",
        }}
      />
      <Container className="relative grid items-center gap-8 py-20 md:grid-cols-[1.3fr_1fr] md:py-24">
        <div>
          <h2 className="font-display text-3xl leading-tight sm:text-4xl">
            {title}
          </h2>
          <p className="mt-4 max-w-xl text-primary-foreground/75">{description}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3 md:justify-end">
          <Button asChild variant="accent" size="lg">
            <Link href="/contacto">Cotizar ahora</Link>
          </Button>
          <Button
            asChild
            size="lg"
            variant="outline"
            className="border-primary-foreground/25 bg-transparent text-primary-foreground hover:bg-primary-foreground/10"
          >
            <a href={company.phoneHref}>{company.phone}</a>
          </Button>
        </div>
      </Container>
    </section>
  );
}
