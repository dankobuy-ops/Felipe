import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Product } from "@/types/product";

export function ProductCard({ product }: { product: Product }) {
  const Icon = product.icon;
  return (
    <Link
      href={`/personas/${product.slug}`}
      className="group relative flex flex-col rounded-2xl border border-border bg-background p-6 shadow-[var(--shadow-card)] transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-[var(--shadow-card-hover)]"
    >
      {product.tag && (
        <Badge
          variant="accent"
          className="absolute right-5 top-5 text-[0.68rem] uppercase tracking-wide"
        >
          {product.tag}
        </Badge>
      )}
      <span className="inline-flex size-11 items-center justify-center rounded-xl bg-primary/5 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
        <Icon className="size-5" />
      </span>
      <h3 className="mt-5 font-display text-xl leading-tight text-foreground">
        {product.title}
      </h3>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
        {product.shortDescription}
      </p>
      <span className="mt-5 inline-flex items-center gap-1 text-sm font-medium text-primary">
        Ver cobertura
        <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}
