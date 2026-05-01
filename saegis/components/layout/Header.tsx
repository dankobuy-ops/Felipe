import Link from "next/link";
import Image from "next/image";
import { Phone } from "lucide-react";
import { asset } from "@/lib/asset";
import { Button } from "@/components/ui/button";
import { Container } from "@/components/ui/container";
import { mainNav } from "@/content/navigation";
import { company } from "@/content/company";
import { MobileNav } from "@/components/layout/MobileNav";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/85 backdrop-blur-md">
      <Container className="flex h-16 items-center justify-between gap-6 md:h-20">
        <Link
          href="/"
          className="flex items-center gap-2 text-primary transition-opacity hover:opacity-90"
          aria-label={`${company.name} — Inicio`}
        >
          <Image
            src={asset("/logo.png")}
            alt={company.name}
            width={200}
            height={200}
            priority
            className="h-10 w-auto md:h-12"
          />
        </Link>

        <nav className="hidden lg:flex items-center gap-1" aria-label="Principal">
          {mainNav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-2 text-sm font-medium text-foreground/80 transition-colors hover:bg-surface hover:text-primary"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <a
            href={company.phoneHref}
            className="hidden items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-foreground/80 transition-colors hover:text-primary md:inline-flex"
          >
            <Phone className="size-4" aria-hidden />
            <span>{company.phone}</span>
          </a>
          <Button asChild variant="accent" size="sm" className="hidden sm:inline-flex">
            <Link href="/contacto">Cotizar</Link>
          </Button>
          <div className="lg:hidden">
            <MobileNav />
          </div>
        </div>
      </Container>
    </header>
  );
}
