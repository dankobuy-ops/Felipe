import { Quote } from "lucide-react";
import { Container } from "@/components/ui/container";
import { testimonials } from "@/content/testimonials";

export function Testimonials() {
  return (
    <section className="section-y bg-surface">
      <Container>
        <div className="mx-auto max-w-2xl text-center">
          <p className="mb-3 text-sm font-medium uppercase tracking-wider text-muted-foreground">
            Clientes
          </p>
          <h2 className="font-display text-3xl text-foreground sm:text-4xl">
            Confianza que se construye con el tiempo.
          </h2>
        </div>
        <ul className="mt-14 grid gap-6 md:grid-cols-3">
          {testimonials.map((t) => (
            <li
              key={t.name}
              className="relative flex flex-col rounded-2xl border border-border bg-background p-7 shadow-[var(--shadow-card)]"
            >
              <Quote className="size-8 text-accent" aria-hidden />
              <p className="mt-5 flex-1 text-[0.95rem] leading-relaxed text-foreground/85">
                “{t.quote}”
              </p>
              <div className="mt-6 border-t border-border pt-5">
                <p className="font-medium text-foreground">{t.name}</p>
                <p className="text-xs text-muted-foreground">{t.role}</p>
              </div>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
