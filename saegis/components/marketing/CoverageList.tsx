import { Check, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Coverage } from "@/types/product";

export function CoverageList({
  coverages,
  variant = "grid",
}: {
  coverages: Coverage[];
  variant?: "grid" | "list";
}) {
  if (variant === "list") {
    return (
      <ul className="space-y-4">
        {coverages.map((c) => (
          <li
            key={c.title}
            className="flex items-start gap-4 rounded-xl border border-border bg-background p-5"
          >
            <span
              className={
                c.highlighted
                  ? "mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent"
                  : "mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/5 text-primary"
              }
            >
              {c.highlighted ? (
                <Sparkles className="size-4" />
              ) : (
                <Check className="size-4" />
              )}
            </span>
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium text-foreground">{c.title}</p>
                {c.optional && (
                  <Badge variant="muted" className="text-[0.65rem] uppercase">
                    Opcional
                  </Badge>
                )}
                {c.highlighted && (
                  <Badge variant="accent" className="text-[0.65rem] uppercase">
                    Destacada
                  </Badge>
                )}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {c.description}
              </p>
            </div>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <ul className="grid gap-4 sm:grid-cols-2">
      {coverages.map((c) => (
        <li
          key={c.title}
          className="flex items-start gap-3 rounded-xl border border-border bg-background p-5"
        >
          <span
            className={
              c.highlighted
                ? "mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent"
                : "mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/5 text-primary"
            }
          >
            <Check className="size-3.5" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium text-foreground">{c.title}</p>
              {c.optional && (
                <Badge variant="muted" className="text-[0.65rem] uppercase">
                  Opcional
                </Badge>
              )}
            </div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {c.description}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
