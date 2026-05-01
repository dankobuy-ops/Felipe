"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, Phone, Mail } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetTitle,
  SheetClose,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { mainNav } from "@/content/navigation";
import { company } from "@/content/company";

export function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          type="button"
          className="inline-flex size-10 items-center justify-center rounded-md border border-border bg-background text-foreground transition-colors hover:bg-surface"
          aria-label="Abrir menú"
        >
          <Menu className="size-5" />
        </button>
      </SheetTrigger>
      <SheetContent className="flex flex-col gap-6">
        <SheetTitle>Menú</SheetTitle>
        <nav className="flex flex-col" aria-label="Principal móvil">
          {mainNav.map((item) => (
            <SheetClose asChild key={item.href}>
              <Link
                href={item.href}
                className="flex items-center justify-between rounded-md px-2 py-3 text-base font-medium text-foreground hover:bg-surface"
              >
                <span>{item.label}</span>
                {item.description && (
                  <span className="text-xs text-muted-foreground">
                    {item.description}
                  </span>
                )}
              </Link>
            </SheetClose>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-3 border-t border-border pt-5 text-sm">
          <a
            href={company.phoneHref}
            className="flex items-center gap-2 text-foreground hover:text-primary"
          >
            <Phone className="size-4" /> {company.phone}
          </a>
          <a
            href={company.emailHref}
            className="flex items-center gap-2 text-foreground hover:text-primary"
          >
            <Mail className="size-4" /> {company.email}
          </a>
          <SheetClose asChild>
            <Button asChild variant="accent">
              <Link href="/contacto">Cotizar ahora</Link>
            </Button>
          </SheetClose>
        </div>
      </SheetContent>
    </Sheet>
  );
}
