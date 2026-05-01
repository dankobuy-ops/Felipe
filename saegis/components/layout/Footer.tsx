import Link from "next/link";
import Image from "next/image";
import { Mail, Phone, MapPin, ShieldCheck } from "lucide-react";
import { asset } from "@/lib/asset";
import { Container } from "@/components/ui/container";
import { company } from "@/content/company";
import { footerNav } from "@/content/navigation";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-border bg-primary text-primary-foreground">
      <Container className="grid gap-10 py-14 md:grid-cols-[1.25fr_1fr_1fr] md:gap-14 md:py-20">
        <div className="space-y-5">
          <Image
            src={asset("/logo.png")}
            alt={company.name}
            width={200}
            height={200}
            className="h-12 w-auto"
          />
          <p className="max-w-sm text-sm leading-relaxed text-primary-foreground/70">
            {company.descriptionShort}
          </p>
          <ul className="space-y-2 text-xs text-primary-foreground/60">
            {company.regulators.map((r) => (
              <li key={r} className="flex items-start gap-2">
                <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-accent" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>

        <nav aria-label="Secundario" className="text-sm">
          <p className="mb-4 font-display text-base">Navegación</p>
          <ul className="grid grid-cols-2 gap-x-6 gap-y-2 text-primary-foreground/75 md:grid-cols-1">
            {footerNav.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className="transition-colors hover:text-accent"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="text-sm">
          <p className="mb-4 font-display text-base">Contacto</p>
          <ul className="space-y-3 text-primary-foreground/80">
            <li className="flex items-start gap-3">
              <Phone className="mt-0.5 size-4 text-accent" />
              <a href={company.phoneHref} className="hover:text-accent">
                {company.phone}
              </a>
            </li>
            <li className="flex items-start gap-3">
              <Mail className="mt-0.5 size-4 text-accent" />
              <a href={company.emailHref} className="hover:text-accent">
                {company.email}
              </a>
            </li>
            <li className="flex items-start gap-3">
              <MapPin className="mt-0.5 size-4 text-accent" />
              <span>
                {company.address.street}, {company.address.city}
                <br />
                {company.address.region}, {company.address.country}
              </span>
            </li>
          </ul>
        </div>
      </Container>

      <div className="border-t border-primary-foreground/10">
        <Container className="flex flex-col items-start justify-between gap-2 py-5 text-xs text-primary-foreground/60 md:flex-row md:items-center">
          <p>© {new Date().getFullYear()} {company.name}. Todos los derechos reservados.</p>
          <p>
            Corredora regulada por la CMF · Asociación Nacional de Seguros (ANS).
          </p>
        </Container>
      </div>
    </footer>
  );
}
