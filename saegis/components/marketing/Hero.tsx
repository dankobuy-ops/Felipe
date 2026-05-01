import Link from "next/link";
import Image from "next/image";
import { asset } from "@/lib/asset";
import { Button } from "@/components/ui/button";
import { Container } from "@/components/ui/container";
import { company } from "@/content/company";

export function Hero() {
  return (
    <section className="relative overflow-hidden bg-primary text-primary-foreground">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 85% 15%, oklch(0.72 0.12 75 / 0.18), transparent 60%), radial-gradient(ellipse 70% 60% at 10% 90%, oklch(0.32 0.09 258 / 0.6), transparent 60%)",
        }}
      />
      <Container className="relative grid items-center gap-14 py-24 md:py-32 lg:grid-cols-[1.15fr_1fr]">
        <div className="space-y-8">
          <span className="inline-flex items-center gap-2 rounded-full border border-primary-foreground/15 bg-primary-foreground/5 px-3 py-1 text-xs font-medium text-primary-foreground/75 backdrop-blur">
            <span className="size-1.5 rounded-full bg-accent" />
            Corredora de seguros · Más de 40 años en Chile
          </span>
          <h1 className="font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl md:text-6xl lg:text-[4rem]">
            Te protegemos a ti,
            <br />
            <span className="text-accent">tu familia</span> y tus inversiones.
          </h1>
          <p className="max-w-xl text-lg leading-relaxed text-primary-foreground/75">
            Asesoría independiente con respaldo de las principales aseguradoras del país. Construimos la cobertura correcta para cada etapa de tu vida, tu negocio o tu comunidad.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button asChild variant="accent" size="lg">
              <Link href="/contacto">Cotizar ahora</Link>
            </Button>
            <Button
              asChild
              size="lg"
              variant="ghost"
              className="text-primary-foreground hover:bg-primary-foreground/10"
            >
              <Link href="/personas">Conoce nuestros seguros →</Link>
            </Button>
          </div>
          <dl className="grid max-w-xl grid-cols-3 gap-6 border-t border-primary-foreground/15 pt-7 text-sm">
            <div>
              <dt className="text-primary-foreground/60">Experiencia</dt>
              <dd className="mt-1 font-display text-2xl text-primary-foreground">
                {company.yearsExperience}+ años
              </dd>
            </div>
            <div>
              <dt className="text-primary-foreground/60">Aseguradoras</dt>
              <dd className="mt-1 font-display text-2xl text-primary-foreground">
                {company.insurers}
              </dd>
            </div>
            <div>
              <dt className="text-primary-foreground/60">Respaldo</dt>
              <dd className="mt-1 font-display text-2xl text-primary-foreground">
                CMF & ANS
              </dd>
            </div>
          </dl>
        </div>

        <div className="relative hidden lg:block">
          <div className="relative mx-auto aspect-[4/5] w-full max-w-md overflow-hidden rounded-3xl shadow-2xl ring-1 ring-primary-foreground/10">
            <Image
              src={asset("/hero-family.png")}
              alt="Familia chilena frente a su hogar al atardecer"
              fill
              sizes="(min-width: 1024px) 28rem, 0px"
              className="object-cover"
              priority
            />
            <div
              aria-hidden
              className="absolute inset-0"
              style={{
                background:
                  "linear-gradient(to top, oklch(0.18 0.04 258 / 0.35) 0%, transparent 40%)",
              }}
            />
            <div className="absolute bottom-6 left-6 right-6 flex items-end justify-between gap-4 text-primary-foreground">
              <p className="font-display text-base leading-snug">
                Protección que cuida
                <br />
                <span className="text-accent">lo que más importa.</span>
              </p>
              <span className="rounded-full border border-primary-foreground/25 bg-primary-foreground/10 px-3 py-1 text-[0.7rem] uppercase tracking-wider backdrop-blur">
                Familias · Chile
              </span>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
