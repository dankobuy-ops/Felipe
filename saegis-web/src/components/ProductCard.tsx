import * as Icons from "lucide-react";
import type { Product } from "@/data/products";

interface Props {
  product: Product;
}

export function ProductCard({ product }: Props) {
  const Icon = (Icons as Record<string, Icons.LucideIcon>)[product.icon] ?? Icons.Shield;
  return (
    <a
      href={`/personas#${product.slug}`}
      className="group relative flex flex-col rounded-2xl border border-(--color-border) bg-(--color-background) p-6 shadow-[var(--shadow-card)] transition-all hover:-translate-y-0.5 hover:border-(--color-primary)/30 hover:shadow-[var(--shadow-card-hover)]"
    >
      {product.tag && (
        <span className="absolute right-5 top-5 inline-flex items-center rounded-full bg-(--color-accent)/15 px-2 py-0.5 text-[0.68rem] font-medium uppercase tracking-wide text-(--color-accent-foreground)">
          {product.tag}
        </span>
      )}
      <span className="inline-flex size-11 items-center justify-center rounded-xl bg-(--color-primary)/5 text-(--color-primary) transition-colors group-hover:bg-(--color-primary) group-hover:text-(--color-primary-foreground)">
        <Icon className="size-5" strokeWidth={2} />
      </span>
      <h3 className="mt-5 font-display text-xl leading-tight text-(--color-foreground)">
        {product.title}
      </h3>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-(--color-muted-foreground)">
        {product.shortDescription}
      </p>
      <span className="mt-5 inline-flex items-center gap-1 text-sm font-medium text-(--color-primary)">
        Ver cobertura
        <Icons.ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" strokeWidth={2} />
      </span>
    </a>
  );
}
