import { ShieldCheck } from "lucide-react";
import { company } from "@/content/company";

export function TrustBadges() {
  return (
    <ul className="flex flex-wrap gap-3 text-xs">
      {company.regulators.map((r) => (
        <li
          key={r}
          className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-muted-foreground"
        >
          <ShieldCheck className="size-3.5 text-primary" /> {r}
        </li>
      ))}
    </ul>
  );
}
