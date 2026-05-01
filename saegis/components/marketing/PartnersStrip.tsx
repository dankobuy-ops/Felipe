import Image from "next/image";
import { asset } from "@/lib/asset";
import { Container } from "@/components/ui/container";
import { partners } from "@/content/partners";

export function PartnersStrip({
  title = "Trabajamos con las principales aseguradoras del país",
  subtitle = "Aseguradoras asociadas",
}: {
  title?: string;
  subtitle?: string;
}) {
  return (
    <section className="border-y border-border bg-background py-16 md:py-20">
      <Container>
        <div className="mx-auto max-w-2xl text-center">
          <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
            {subtitle}
          </p>
          <h2 className="font-display text-2xl text-foreground sm:text-3xl">
            {title}
          </h2>
        </div>
        <ul className="mt-12 grid grid-cols-3 items-center gap-x-8 gap-y-10 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-6">
          {partners.map((p) => (
            <li
              key={p.slug}
              className="flex items-center justify-center text-muted-foreground/80 transition-colors hover:text-primary"
              title={p.name}
            >
              <Image
                src={asset(`/images/partners/${p.slug}.${p.ext}`)}
                alt={p.name}
                width={p.width}
                height={p.height}
                className="h-8 w-auto opacity-70 transition-opacity hover:opacity-100 md:h-9"
              />
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
